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


def render_bone_frame(img_rgba, bones, frame_data, scale=1):
    """Render a single frame by applying bone transforms to the character image.

    Simplified approach: apply subtle transforms (shift, rotate) to body part
    regions based on bone angles, then composite onto a clean canvas.
    """
    h, w = img_rgba.shape[:2]
    canvas = np.zeros((h, w, 4), dtype=np.uint8)

    # For a front-facing sprite, we apply transforms as subtle pixel shifts
    # rather than full skeletal deformation (which would require mesh skinning).
    # The visual effect comes from slight position offsets of body regions.

    # Get hip offset (applies to everything)
    hip_dy = frame_data.get("hip", {}).get("y", 0)

    # Copy the whole image as base
    result = img_rgba.copy()

    # Apply subtle vertical bob to simulate walk bounce
    bob = int(round(hip_dy))
    if bob != 0:
        M = np.float32([[1, 0, 0], [0, 1, -bob]])
        result = cv2.warpAffine(result, M, (w, h), borderMode=cv2.BORDER_CONSTANT)

    return result


def render_walk_frames(img_rgba, bones, walk_frames, parts):
    """Render 8 walk frames with programmatic animation.

    Instead of skeletal deformation (complex), we use cutout animation:
    - Slight vertical bounce
    - Subtle horizontal sway
    - Leg/arm region shifts for stride effect
    """
    h, w = img_rgba.shape[:2]
    frames = []

    # Extract body part regions from the original image
    part_regions = {}
    for name, (px, py, pw, ph) in parts.items():
        px = max(0, px)
        py = max(0, py)
        pw = min(pw, w - px)
        ph = min(ph, h - py)
        if pw > 0 and ph > 0:
            part_regions[name] = img_rgba[py:py+ph, px:px+pw].copy()

    for fi, frame_data in enumerate(walk_frames):
        canvas = np.zeros((h, w, 4), dtype=np.uint8)

        # Global bounce
        hip_dy = int(round(frame_data.get("hip", {}).get("y", 0)))
        spine_sway = frame_data.get("spine", {}).get("skZ", 0)

        # Place torso (slight sway)
        tx, ty, tw, th = parts["torso"]
        sway_px = int(round(spine_sway * 0.5))
        canvas[ty-hip_dy:ty-hip_dy+th, tx+sway_px:tx+sway_px+tw] = \
            img_rgba[ty:ty+th, tx:tx+tw]

        # Place head
        hx, hy, hw, hh = parts["head"]
        head_sway = int(round(frame_data.get("head", {}).get("skZ", 0) * 0.3))
        canvas[hy-hip_dy:hy-hip_dy+hh, hx+sway_px+head_sway:hx+sway_px+head_sway+hw] = \
            img_rgba[hy:hy+hh, hx:hx+hw]

        # Left leg - shift based on leg angle
        l_upper = frame_data.get("left_upper_leg", {}).get("skZ", 0)
        l_shift = int(round(math.sin(math.radians(l_upper)) * 4))
        lx, ly, lw, lh = parts["left_leg"]
        canvas[ly-hip_dy:ly-hip_dy+lh, lx+l_shift:lx+l_shift+lw] = \
            img_rgba[ly:ly+lh, lx:lx+lw]

        # Right leg - opposite phase
        r_upper = frame_data.get("right_upper_leg", {}).get("skZ", 0)
        r_shift = int(round(math.sin(math.radians(r_upper)) * 4))
        rx, ry, rw, rh = parts["right_leg"]
        canvas[ry-hip_dy:ry-hip_dy+rh, rx+r_shift:rx+r_shift+rw] = \
            img_rgba[ry:ry+rh, rx:rx+rw]

        # Left arm - slight swing
        l_arm_angle = frame_data.get("left_upper_arm", {}).get("skZ", 0)
        la_shift = int(round(math.sin(math.radians(l_arm_angle)) * 3))
        lax, lay, law, lah = parts["left_arm"]
        canvas[lay-hip_dy:lay-hip_dy+lah, lax+la_shift:lax+la_shift+law] = \
            img_rgba[lay:lay+lah, lax:lax+law]

        # Right arm
        r_arm_angle = frame_data.get("right_upper_arm", {}).get("skZ", 0)
        ra_shift = int(round(math.sin(math.radians(r_arm_angle)) * 3))
        rax, ray_raw, raw, rah = parts["right_arm"]
        canvas[ray_raw-hip_dy:ray_raw-hip_dy+rah, rax+ra_shift:rax+ra_shift+raw] = \
            img_rgba[ray_raw:ray_raw+rah, rax:rax+raw]

        # Fill any gaps from shifts by copying background
        # (pixels that were in original but not in transformed regions)
        mask = cv2.bitwise_not(cv2.cvtColor(canvas, cv2.COLOR_BGRA2GRAY))
        mask = (mask > 0).astype(np.uint8) * 255
        # Only fill where original has content and canvas is empty
        orig_alpha = img_rgba[:, :, 3]
        fill_mask = cv2.bitwise_and(mask, (orig_alpha > 30).astype(np.uint8) * 255)
        for c in range(4):
            canvas[:, :, c] = np.where(fill_mask > 0, img_rgba[:, :, c], canvas[:, :, c])

        frames.append(canvas)

    return frames


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
