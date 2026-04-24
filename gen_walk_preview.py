#!/usr/bin/env python3
"""
gen_walk_preview.py — Generate walking GIF preview for all 4 directions.
Uses dragonbones_rig.py body part detection + programmatic walk animation.

Usage:
    python3 gen_walk_preview.py              # all characters
    python3 gen_walk_preview.py --char kai   # single character
"""
import argparse
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from dragonbones_rig import detect_body_parts, build_skeleton, generate_walk_cycle_direction

SPRITES_DIR = Path("assets/sprites")
OUTPUT_DIR = Path("assets/sprites/previews")
FRAME_W, FRAME_H = 128, 128
WALK_FRAMES = 8
GIF_SCALE = 3  # upscale for visibility
GIF_FPS = 10


def rotate_region(img_rgba, cx, cy, angle_deg, region_x, region_y, region_w, region_h):
    """Rotate a body part region around its anchor point (top-center for limbs)."""
    h, w = img_rgba.shape[:2]
    rx1 = max(0, region_x)
    ry1 = max(0, region_y)
    rx2 = min(w, region_x + region_w)
    ry2 = min(h, region_y + region_h)
    if rx2 <= rx1 or ry2 <= ry1:
        return img_rgba.copy()

    region = img_rgba[ry1:ry2, rx1:rx2].copy()
    rh, rw = region.shape[:2]

    pivot_x = rw / 2
    pivot_y = 0

    M = cv2.getRotationMatrix2D((pivot_x, pivot_y), angle_deg, 1.0)
    rotated = cv2.warpAffine(region, M, (rw, rh), borderMode=cv2.BORDER_CONSTANT)

    result = img_rgba.copy()
    result[ry1:ry2, rx1:rx2] = rotated
    return result


def render_walk_frames(img_rgba, bones, walk_frames, parts):
    """Render 8 walk frames with proper joint articulation.

    Each limb is split into upper/lower segments.
    Upper rotates from shoulder/hip pivot.
    Lower rotates from elbow/knee pivot, inheriting parent rotation.
    """
    h, w = img_rgba.shape[:2]
    frames = []

    for fi, frame_data in enumerate(walk_frames):
        canvas = np.zeros((h, w, 4), dtype=np.uint8)

        # ── Global transforms ──
        hip_dy = frame_data.get("hip", {}).get("y", 0)
        spine_sway = frame_data.get("spine", {}).get("skZ", 0)
        head_sway = frame_data.get("head", {}).get("skZ", 0)

        bounce = int(round(hip_dy * 1.5))
        sway = int(round(spine_sway * 1.2))

        # ── Helper: rotate a region around its top-center, paste onto canvas ──
        def draw_rotated(src_img, part_key, angle_deg, extra_dx=0, extra_dy=0):
            if part_key not in parts:
                return
            px, py, pw, ph = int(parts[part_key][0]), int(parts[part_key][1]), int(parts[part_key][2]), int(parts[part_key][3])
            region = src_img[max(0,py):min(h,py+ph), max(0,px):min(w,px+pw)].copy()
            if region.size == 0 or pw == 0 or ph == 0:
                return
            center = (pw // 2, 0)
            M = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
            rotated = cv2.warpAffine(region, M, (pw, ph), borderMode=cv2.BORDER_CONSTANT)
            paste_region(canvas, rotated, px + sway // 2 + extra_dx, py - bounce + extra_dy, w, h)

        # ── 1. Legs (behind torso) ──
        # Upper legs rotate from hip, lower legs inherit + add knee bend
        for side in ("left", "right"):
            upper_key = f"{side}_upper_leg"
            lower_key = f"{side}_lower_leg"
            upper_data = frame_data.get(upper_key, {})
            lower_angle = frame_data.get(lower_key, {}).get("skZ", 0)
            upper_angle = upper_data.get("skZ", 0)
            leg_dx = int(round(upper_data.get("x", 0)))  # horizontal stride
            leg_dy = int(round(upper_data.get("y", 0)))  # vertical lift

            # Draw upper leg with rotation + offset (horizontal stride + lift)
            if upper_key in parts:
                px, py, pw, ph = int(parts[upper_key][0]), int(parts[upper_key][1]), int(parts[upper_key][2]), int(parts[upper_key][3])
                region = img_rgba[max(0,py):min(h,py+ph), max(0,px):min(w,px+pw)].copy()
                if region.size > 0 and pw > 0 and ph > 0:
                    center = (pw // 2, 0)
                    M = cv2.getRotationMatrix2D(center, -upper_angle, 1.0)
                    rotated = cv2.warpAffine(region, M, (pw, ph), borderMode=cv2.BORDER_CONSTANT)
                    paste_region(canvas, rotated, px + sway // 2 + leg_dx, py - bounce + leg_dy, w, h)

            # Lower leg: inherit upper rotation + knee bend + offset
            if lower_key in parts:
                lx, ly, lw, lh = int(parts[lower_key][0]), int(parts[lower_key][1]), int(parts[lower_key][2]), int(parts[lower_key][3])
                region = img_rgba[max(0,ly):min(h,ly+lh), max(0,lx):min(w,lx+lw)].copy()
                if region.size > 0 and lw > 0 and lh > 0:
                    combined_angle = upper_angle + lower_angle
                    center = (lw // 2, 0)
                    M = cv2.getRotationMatrix2D(center, -combined_angle, 1.0)
                    rotated = cv2.warpAffine(region, M, (lw, lh), borderMode=cv2.BORDER_CONSTANT)
                    paste_region(canvas, rotated, lx + sway // 2 + leg_dx, ly - bounce + leg_dy, w, h)

        # ── 2. Arms (behind torso for side views) ──
        for side in ("left", "right"):
            upper_key = f"{side}_upper_arm"
            lower_key = f"{side}_lower_arm"
            upper_angle = frame_data.get(upper_key, {}).get("skZ", 0)
            lower_angle = frame_data.get(lower_key, {}).get("skZ", 0)

            # Upper arm rotates from shoulder
            draw_rotated(img_rgba, upper_key, upper_angle)

            # Lower arm: inherit upper + own elbow bend
            if lower_key in parts:
                ax, ay, aw, ah = int(parts[lower_key][0]), int(parts[lower_key][1]), int(parts[lower_key][2]), int(parts[lower_key][3])
                region = img_rgba[max(0,ay):min(h,ay+ah), max(0,ax):min(w,ax+aw)].copy()
                if region.size > 0 and aw > 0 and ah > 0:
                    combined_angle = upper_angle + lower_angle
                    center = (aw // 2, 0)
                    M = cv2.getRotationMatrix2D(center, -combined_angle, 1.0)
                    rotated = cv2.warpAffine(region, M, (aw, ah), borderMode=cv2.BORDER_CONSTANT)
                    paste_region(canvas, rotated, ax + sway // 2, ay - bounce, w, h)

        # ── 3. Torso (on top of limbs) ──
        draw_rotated(img_rgba, "torso", spine_sway)

        # ── 4. Head (on top) ──
        if "head" in parts:
            hx, hy, hw, hh = int(parts["head"][0]), int(parts["head"][1]), int(parts["head"][2]), int(parts["head"][3])
            dst_x = hx + sway + int(round(head_sway * 0.8))
            dst_y = hy - bounce - 1
            paste_region(canvas, img_rgba[hy:hy+hh, hx:hx+hw], dst_x, dst_y, w, h)

        # ── 5. Fill gaps ──
        alpha = canvas[:, :, 3]
        gap_mask = (alpha < 30).astype(np.uint8) * 255
        orig_alpha = img_rgba[:, :, 3]
        fill = cv2.bitwise_and(gap_mask, (orig_alpha > 30).astype(np.uint8) * 255)
        for c in range(4):
            canvas[:, :, c] = np.where(fill > 0, img_rgba[:, :, c], canvas[:, :, c])

        frames.append(canvas)

    return frames


def paste_region(canvas, region, dst_x, dst_y, canvas_w, canvas_h):
    """Paste a region onto canvas with bounds clipping."""
    rh, rw = region.shape[:2]
    # Source region (full)
    sx1, sy1 = 0, 0
    sx2, sy2 = rw, rh
    # Destination (clipped to canvas)
    dx1 = max(0, dst_x)
    dy1 = max(0, dst_y)
    dx2 = min(canvas_w, dst_x + rw)
    dy2 = min(canvas_h, dst_y + rh)
    if dx2 <= dx1 or dy2 <= dy1:
        return
    # Corresponding source pixels
    sx1 += dx1 - dst_x
    sy1 += dy1 - dst_y
    sx2 = sx1 + (dx2 - dx1)
    sy2 = sy1 + (dy2 - dy1)
    canvas[dy1:dy2, dx1:dx2] = region[sy1:sy2, sx1:sx2]


def make_gif(direction_frames, out_path, scale=3, fps=10):
    """Combine 4 directions into a single GIF: each direction as a row."""
    # Layout: 4 rows (down, left, right, up), each row = 8 frames
    row_h = FRAME_H * scale
    col_w = FRAME_W * scale
    total_w = col_w * WALK_FRAMES
    total_h = row_h * 4

    gif_frames = []
    # For each frame index, compose all 4 directions side by side
    for fi in range(WALK_FRAMES):
        canvas = Image.new("RGBA", (total_w, total_h), (20, 20, 40, 255))

        for row, dir_name in enumerate(["down", "left", "right", "up"]):
            if dir_name not in direction_frames:
                continue
            frames = direction_frames[dir_name]
            if fi >= len(frames):
                continue

            frame = frames[fi]
            # Convert numpy to PIL
            frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA))
            frame_pil = frame_pil.resize((col_w, row_h), Image.NEAREST)

            # Add direction label
            from PIL import ImageDraw
            draw = ImageDraw.Draw(frame_pil)
            draw.text((4, 4), dir_name.upper(), fill=(255, 255, 255, 200))

            canvas.paste(frame_pil, (0, row * row_h))

        gif_frames.append(canvas.convert("RGB"))

    # Save GIF
    duration = int(1000 / fps)
    gif_frames[0].save(
        str(out_path),
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration,
        loop=0,
    )
    print(f"  💾 Saved: {out_path} ({len(gif_frames)} frames, {fps} fps)")


def process_character(char_id):
    """Process a single character: detect parts, rig, animate, GIF."""
    print(f"\n{'='*50}")
    print(f"🎬 {char_id}")
    print(f"{'='*50}")

    direction_frames = {}

    for direction in ["down", "left", "right", "up"]:
        cutout_path = SPRITES_DIR / f"cutout_{char_id}_{direction}.png"
        if not cutout_path.exists():
            print(f"  ⚠️  Missing: {cutout_path}")
            continue

        print(f"\n  📐 {direction}: {cutout_path}")

        # Load image
        img = cv2.imread(str(cutout_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"  ❌ Failed to load")
            continue

        print(f"     Size: {img.shape[1]}x{img.shape[0]}")

        # Detect body parts
        parts = detect_body_parts(img)
        if not parts:
            print(f"  ❌ No body parts detected")
            continue

        for name, (x, y, w, h) in parts.items():
            print(f"     {name}: ({x},{y}) {w}x{h}")

        # Build skeleton
        bones = build_skeleton(parts, img.shape[1], img.shape[0])
        print(f"     Skeleton: {len(bones)} bones")

        # Generate walk cycle
        walk_frames = generate_walk_cycle_direction(bones, direction, WALK_FRAMES)
        print(f"     Walk frames: {len(walk_frames)}")

        # Render frames
        rendered = render_walk_frames(img, bones, walk_frames, parts)
        direction_frames[direction] = rendered
        print(f"     Rendered: {len(rendered)} frames")

    if direction_frames:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        gif_path = OUTPUT_DIR / f"{char_id}_walk.gif"
        make_gif(direction_frames, gif_path, scale=GIF_SCALE, fps=GIF_FPS)
    else:
        print(f"  ❌ No frames generated")


def main():
    parser = argparse.ArgumentParser(description="Walk GIF preview generator")
    parser.add_argument("--char", type=str, help="Single character to process")
    args = parser.parse_args()

    if args.char:
        process_character(args.char)
    else:
        # Find all characters with cutout images
        chars = set()
        for f in SPRITES_DIR.glob("cutout_*_down.png"):
            char_id = f.stem.replace("cutout_", "").replace("_down", "")
            chars.add(char_id)
        for char_id in sorted(chars):
            process_character(char_id)


if __name__ == "__main__":
    main()
