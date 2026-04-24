#!/usr/bin/env python3
"""
dragonbones_rig.py — Auto-rig front-facing character sprite + generate walk cycle

Takes a single front-facing character image, auto-detects body part regions,
creates a DragonBones skeleton, and generates an 8-frame walk cycle animation.

Usage:
    python3 dragonbones_rig.py assets/sprites/cutout_joker_down.png -o joker_rig
    python3 dragonbones_rig.py assets/sprites/cutout_kai_down.png -o kai_rig --preview
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import cv2


# ── Body Part Detection ────────────────────────────────────────────

def detect_body_parts(img_rgba):
    """Detect body part bounding boxes from a front-facing character image.

    Uses alpha channel + vertical projection to find neck as a local width
    minimum, then splits the character into head / torso / legs proportionally.
    Arms are detected from pixels that extend beyond the torso envelope.

    Returns dict of {part: (x, y, w, h)} in pixel coords.
    """
    h, w = img_rgba.shape[:2]
    alpha = img_rgba[:, :, 3] if img_rgba.shape[2] == 4 else np.ones((h, w), dtype=np.uint8) * 255

    mask = (alpha > 30).astype(np.uint8)

    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None

    char_x1, char_x2 = xs.min(), xs.max()
    char_y1, char_y2 = ys.min(), ys.max()
    char_w = char_x2 - char_x1
    char_h = char_y2 - char_y1

    # Row widths
    v_proj = mask.sum(axis=1).astype(np.float32)

    # ── Find NECK by local minimum in upper 45% ──
    scan_end = char_y1 + int(char_h * 0.45)
    neck_y = char_y1 + int(char_h * 0.22)  # default fallback
    min_neck_width = 1e9

    for y in range(char_y1 + int(char_h * 0.10), scan_end):
        rw = v_proj[y]
        if rw < min_neck_width:
            min_neck_width = rw
            neck_y = y

    # ── Head: char_y1 → neck_y ──
    head_top = char_y1
    head_bottom = neck_y

    # Head bbox from mask pixels in head region
    head_region = mask[head_top:head_bottom, :]
    head_h_proj = head_region.sum(axis=0)
    head_xs = np.where(head_h_proj > 0)[0]
    if len(head_xs) > 0:
        head_x1, head_x2 = head_xs.min(), head_xs.max()
    else:
        head_x1 = char_x1 + int(char_w * 0.25)
        head_x2 = char_x2 - int(char_w * 0.25)

    # ── Torso: neck_y → ~55% of character height ──
    torso_top = neck_y
    torso_bottom = char_y1 + int(char_h * 0.55)

    torso_region = mask[torso_top:torso_bottom, :]
    torso_h_proj = torso_region.sum(axis=0)
    torso_xs = np.where(torso_h_proj > 0)[0]
    if len(torso_xs) > 0:
        torso_x1, torso_x2 = torso_xs.min(), torso_xs.max()
    else:
        torso_x1 = char_x1 + int(char_w * 0.2)
        torso_x2 = char_x2 - int(char_w * 0.2)

    torso_cx = (torso_x1 + torso_x2) // 2
    torso_w = torso_x2 - torso_x1

    # ── Legs: torso_bottom → char_y2 ──
    legs_top = torso_bottom
    legs_bottom = char_y2

    leg_region = mask[legs_top:legs_bottom, :]
    leg_h_proj = leg_region.sum(axis=0)

    # Split legs at center gap
    center_x = torso_cx
    gap_range = int(torso_w * 0.3)
    cs = max(0, center_x - gap_range)
    ce = min(w, center_x + gap_range)
    center_profile = leg_h_proj[cs:ce]
    left_leg_x2 = center_x - 2
    right_leg_x1 = center_x + 2

    if len(center_profile) > 4:
        kernel = np.ones(3) / 3
        smoothed = np.convolve(center_profile, kernel, mode='same')
        min_idx = np.argmin(smoothed)
        gap_x = cs + min_idx
        left_leg_x2 = gap_x - 1
        right_leg_x1 = gap_x + 1

    left_leg_mask = leg_region[:, :left_leg_x2]
    lxs = np.where(left_leg_mask.sum(axis=0) > 0)[0]
    left_leg_x1 = lxs.min() if len(lxs) > 0 else torso_x1

    right_leg_mask = leg_region[:, right_leg_x1:]
    rxs = np.where(right_leg_mask.sum(axis=0) > 0)[0]
    right_leg_x2 = (right_leg_x1 + rxs.max()) if len(rxs) > 0 else torso_x2

    # ── Arms: take strips from torso sides ──
    # For pixel art characters, arms are usually integrated into the body
    # silhouette.  We extract thin strips from the left/right edges of the
    # torso region as arm segments.  If those strips have enough content,
    # use them; otherwise fall back to zero-width stubs.
    arm_top = torso_top + int((torso_bottom - torso_top) * 0.05)
    arm_bottom = min(char_y2, torso_top + int((torso_bottom - torso_top) * 1.0))
    arm_strip_w = max(8, int(torso_w * 0.15))  # ~15% of torso width per arm

    # Left arm strip
    left_arm_x1 = max(0, torso_x1)
    left_arm_x2 = min(torso_x1 + arm_strip_w, torso_x2)
    left_arm_region = mask[arm_top:arm_bottom, left_arm_x1:left_arm_x2]
    left_arm_content = np.sum(left_arm_region > 0)

    # Right arm strip
    right_arm_x1 = max(torso_x2 - arm_strip_w, torso_x1)
    right_arm_x2 = min(w, torso_x2)
    right_arm_region = mask[arm_top:arm_bottom, right_arm_x1:right_arm_x2]
    right_arm_content = np.sum(right_arm_region > 0)

    # If strips don't have enough content, shrink to minimal stubs
    # (the walk animation will still work via torso rotation)
    if left_arm_content < 10:
        left_arm_x1 = torso_x1
        left_arm_x2 = torso_x1 + max(4, arm_strip_w // 3)
    if right_arm_content < 10:
        right_arm_x1 = torso_x2 - max(4, arm_strip_w // 3)
        right_arm_x2 = torso_x2

    parts = {
        "head":     (head_x1, head_top, head_x2 - head_x1, head_bottom - head_top),
        "torso":    (torso_x1, torso_top, torso_x2 - torso_x1, torso_bottom - torso_top),
        "left_arm": (left_arm_x1, arm_top, left_arm_x2 - left_arm_x1, arm_bottom - arm_top),
        "right_arm":(right_arm_x1, arm_top, right_arm_x2 - right_arm_x1, arm_bottom - arm_top),
        "left_leg": (left_leg_x1, legs_top, left_leg_x2 - left_leg_x1, legs_bottom - legs_top),
        "right_leg":(right_leg_x1, legs_top, right_leg_x2 - right_leg_x1, legs_bottom - legs_top),
    }

    # ── Split limbs into upper/lower segments (knee/elbow at ~50%) ──
    for side in ("left", "right"):
        # Legs: split at knee (50% height)
        lx, ly, lw, lh = parts[f"{side}_leg"]
        knee_y = ly + int(lh * 0.50)
        upper_h = knee_y - ly
        lower_h = lh - upper_h
        parts[f"{side}_upper_leg"] = (lx, ly, lw, upper_h)
        parts[f"{side}_lower_leg"] = (lx, knee_y, lw, lower_h)

        # Arms: split at elbow (50% height)
        ax, ay, aw, ah = parts[f"{side}_arm"]
        elbow_y = ay + int(ah * 0.50)
        upper_ah = elbow_y - ay
        lower_ah = ah - upper_ah
        parts[f"{side}_upper_arm"] = (ax, ay, aw, upper_ah)
        parts[f"{side}_lower_arm"] = (ax, elbow_y, aw, lower_ah)

    return parts


# ── Skeleton Generation ────────────────────────────────────────────

def build_skeleton(parts, img_w, img_h):
    """Build DragonBones skeleton from detected body parts.

    Bone hierarchy:
        root
        └── hip (center bottom of torso)
            ├── spine (torso center)
            │   ├── head
            │   ├── left_upper_arm
            │   │   └── left_lower_arm
            │   └── right_upper_arm
            │       └── right_lower_arm
            ├── left_upper_leg
            │   └── left_lower_leg
            └── right_upper_leg
                └── right_lower_leg
    """
    # Convert pixel coords to DragonBones coords (origin at center, y-up)
    def px_to_db(px, py):
        """Pixel (top-left origin) → DragonBones (center origin, y-up)."""
        dbx = px - img_w / 2
        dby = -(py - img_h / 2)
        return dbx, dby

    # Key anchor points
    hip_px = (parts["torso"][0] + parts["torso"][2] / 2,
              parts["torso"][1] + parts["torso"][3])
    spine_px = (parts["torso"][0] + parts["torso"][2] / 2,
                parts["torso"][1] + parts["torso"][3] * 0.5)
    head_px = (parts["head"][0] + parts["head"][2] / 2,
               parts["head"][1] + parts["head"][3] * 0.5)
    head_top_px = (parts["head"][0] + parts["head"][2] / 2,
                   parts["head"][1])

    # Arm anchor points (shoulders)
    l_shoulder_px = (parts["torso"][0] + parts["torso"][2] * 0.15,
                     parts["torso"][1] + parts["torso"][3] * 0.15)
    r_shoulder_px = (parts["torso"][0] + parts["torso"][2] * 0.85,
                     parts["torso"][1] + parts["torso"][3] * 0.15)

    # Arm mid/ends
    l_arm_cx = parts["left_arm"][0] + parts["left_arm"][2] / 2
    r_arm_cx = parts["right_arm"][0] + parts["right_arm"][2] / 2
    l_arm_mid = (l_arm_cx, parts["left_arm"][1] + parts["left_arm"][3] * 0.5)
    r_arm_mid = (r_arm_cx, parts["right_arm"][1] + parts["right_arm"][3] * 0.5)
    l_arm_end = (l_arm_cx, parts["left_arm"][1] + parts["left_arm"][3])
    r_arm_end = (r_arm_cx, parts["right_arm"][1] + parts["right_arm"][3])

    # Leg anchor points (hips)
    l_hip_px = (parts["left_leg"][0] + parts["left_leg"][2] / 2,
                parts["left_leg"][1])
    r_hip_px = (parts["right_leg"][0] + parts["right_leg"][2] / 2,
                parts["right_leg"][1])

    # Leg mid/ends
    l_leg_mid = (l_hip_px[0], parts["left_leg"][1] + parts["left_leg"][3] * 0.5)
    r_leg_mid = (r_hip_px[0], parts["right_leg"][1] + parts["right_leg"][3] * 0.5)
    l_leg_end = (l_hip_px[0], parts["left_leg"][1] + parts["left_leg"][3])
    r_leg_end = (r_hip_px[0], parts["right_leg"][1] + parts["right_leg"][3])

    # Build bone list with parent indices
    # Format: (name, parent_idx, pixel_pos, length)
    bones = []
    bones.append(("root",         -1, (img_w/2, img_h),     0))           # 0
    bones.append(("hip",           0, hip_px,                0))           # 1
    bones.append(("spine",         1, spine_px,              dist(spine_px, hip_px)))  # 2
    bones.append(("head",          2, head_px,               dist(head_px, head_top_px)))  # 3
    bones.append(("left_upper_arm",2, l_shoulder_px,         dist(l_shoulder_px, l_arm_mid)))  # 4
    bones.append(("left_lower_arm",4, l_arm_mid,             dist(l_arm_mid, l_arm_end)))  # 5
    bones.append(("right_upper_arm",2, r_shoulder_px,        dist(r_shoulder_px, r_arm_mid)))  # 6
    bones.append(("right_lower_arm",6, r_arm_mid,            dist(r_arm_mid, r_arm_end)))  # 7
    bones.append(("left_upper_leg",1, l_hip_px,              dist(l_hip_px, l_leg_mid)))  # 8
    bones.append(("left_lower_leg",8, l_leg_mid,             dist(l_leg_mid, l_leg_end)))  # 9
    bones.append(("right_upper_leg",1, r_hip_px,             dist(r_hip_px, r_leg_mid)))  # 10
    bones.append(("right_lower_leg",10, r_leg_mid,           dist(r_leg_mid, r_leg_end)))  # 11

    # Convert to DragonBones format
    db_bones = []
    for i, (name, parent_idx, pixel_pos, length) in enumerate(bones):
        dbx, dby = px_to_db(*pixel_pos)
        parent_name = bones[parent_idx][0] if parent_idx >= 0 else ""
        db_bones.append({
            "name": name,
            "parent": parent_name,
            "length": round(length, 1),
            "transform": {
                "x": round(dbx, 1),
                "y": round(dby, 1),
                "skX": 0,
                "skY": 0,
                "scX": 1,
                "scY": 1
            }
        })

    return db_bones


def dist(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


# ── Walk Cycle Animation ───────────────────────────────────────────

def generate_walk_cycle(bones, num_frames=8):
    """Generate 8-frame front-facing walk cycle animation keyframes.

    Walk cycle phases (front view):
        Frame 0: Right foot forward, left arm forward (contact)
        Frame 1: Passing (legs cross)
        Frame 2: Left foot forward, right arm forward (contact)
        Frame 3: Passing (legs cross)
        Frame 4-7: Repeat mirror

    Returns list of frame dicts with bone transforms.
    """
    frames = []

    for f in range(num_frames):
        t = f / num_frames  # 0→1
        phase = t * 2 * math.pi

        frame = {}

        # Hip: slight vertical bob (2px amplitude)
        hip_bob = math.sin(phase * 2) * 1.5
        frame["hip"] = {"y": round(hip_bob, 2)}

        # Spine: slight rotation (sway)
        spine_sway = math.sin(phase) * 1.5
        frame["spine"] = {"skZ": round(spine_sway, 2), "y": round(hip_bob * 0.5, 2)}

        # Head: opposite sway (stabilizes)
        head_sway = -spine_sway * 0.3
        frame["head"] = {"skZ": round(head_sway, 2)}

        # ── Legs ──
        leg_swing = 18  # degrees
        knee_bend = 15  # degrees

        # Left leg: forward at frame 0, 4
        l_leg_phase = phase
        l_upper_angle = math.sin(l_leg_phase) * leg_swing
        # Knee bends when leg swings forward (positive angle = forward)
        l_knee_bend = max(0, math.sin(l_leg_phase)) * knee_bend

        frame["left_upper_leg"] = {"skZ": round(l_upper_angle, 2)}
        frame["left_lower_leg"] = {"skZ": round(l_knee_bend, 2)}

        # Right leg: opposite phase
        r_leg_phase = phase + math.pi
        r_upper_angle = math.sin(r_leg_phase) * leg_swing
        r_knee_bend = max(0, math.sin(r_leg_phase)) * knee_bend

        frame["right_upper_leg"] = {"skZ": round(r_upper_angle, 2)}
        frame["right_lower_leg"] = {"skZ": round(r_knee_bend, 2)}

        # ── Arms ── (opposite to legs)
        arm_swing = 15  # degrees
        elbow_bend = 12

        # Left arm: opposite to left leg
        l_arm_phase = phase + math.pi
        l_upper_arm_angle = math.sin(l_arm_phase) * arm_swing
        l_elbow_bend = max(0, math.sin(l_arm_phase)) * elbow_bend

        frame["left_upper_arm"] = {"skZ": round(l_upper_arm_angle, 2)}
        frame["left_lower_arm"] = {"skZ": round(l_elbow_bend, 2)}

        # Right arm: opposite to right leg
        r_arm_phase = phase
        r_upper_arm_angle = math.sin(r_arm_phase) * arm_swing
        r_elbow_bend = max(0, math.sin(r_arm_phase)) * elbow_bend

        frame["right_upper_arm"] = {"skZ": round(r_upper_arm_angle, 2)}
        frame["right_lower_arm"] = {"skZ": round(r_elbow_bend, 2)}

        frames.append(frame)

    return frames


# ── Walk Cycle by Direction ────────────────────────────────────────

def generate_walk_cycle_direction(bones, direction, num_frames=8):
    """Generate walk cycle with direction-specific parameters.

    Calibrated against official DragonBones DragonBoy walk data:
    - Upper leg: ±45° (DragonBoy: ±90°, halved for 2D cutout)
    - Lower leg: ±55° (DragonBoy: ±84°-114°)
    - Upper arm: ±35° (DragonBoy: ±51°-120°)
    - Lower arm: ±25° (DragonBoy: ±17°-45°)
    - Hand: ±20° (DragonBoy: ±30°-45°)
    - Hip bob: 12px (DragonBoy: 25px)
    - Spine sway: ±8° (DragonBoy: implicit in body)
    - Head: ±5° (DragonBoy: ±10°)
    - Scale: 1.0-1.06 (DragonBoy: 1.0-1.14)
    """
    frames = []

    for f in range(num_frames):
        t = f / num_frames
        phase = t * 2 * math.pi
        frame = {}

        if direction in ("down", "up"):
            arm_mult = 1.0 if direction == "down" else 0.7
            leg_swing = 45
            knee_bend = 55
            arm_swing = 35 * arm_mult
            elbow_bend = 25 * arm_mult
            hand_swing = 20 * arm_mult

            # Body: hip bob + spine sway + head counter-sway
            hip_bob = math.sin(phase * 2) * 12
            spine_sway = math.sin(phase) * 8
            frame["hip"] = {"y": round(hip_bob, 2)}
            frame["spine"] = {"skZ": round(spine_sway, 2), "y": round(hip_bob * 0.3, 2)}
            frame["head"] = {"skZ": round(-spine_sway * 0.6, 2)}

            # Legs: cross motion with scale change
            l_leg = math.sin(phase) * leg_swing
            l_scale = 1.0 + max(0, math.sin(phase)) * 0.06
            r_scale = 1.0 + max(0, -math.sin(phase)) * 0.06
            frame["left_upper_leg"] = {"skZ": round(l_leg, 2), "scY": round(l_scale, 3)}
            frame["left_lower_leg"] = {"skZ": round(max(0, math.sin(phase)) * knee_bend, 2)}
            frame["right_upper_leg"] = {"skZ": round(-l_leg, 2), "scY": round(r_scale, 3)}
            frame["right_lower_leg"] = {"skZ": round(max(0, -math.sin(phase)) * knee_bend, 2)}

            # Arms: counter-swing to legs, with elbow bend
            l_arm = math.sin(phase + math.pi) * arm_swing
            frame["left_upper_arm"] = {"skZ": round(l_arm, 2)}
            frame["left_lower_arm"] = {"skZ": round(max(0, math.sin(phase + math.pi)) * elbow_bend, 2)}
            frame["right_upper_arm"] = {"skZ": round(-l_arm, 2)}
            frame["right_lower_arm"] = {"skZ": round(max(0, -math.sin(phase + math.pi)) * elbow_bend, 2)}

            # Hands: subtle wrist motion
            frame["left_hand"] = {"skZ": round(math.sin(phase + math.pi) * hand_swing, 2)}
            frame["right_hand"] = {"skZ": round(-math.sin(phase + math.pi) * hand_swing, 2)}

        elif direction == "right":
            hip_bob = math.sin(phase * 2) * 12
            body_lean = math.sin(phase) * 8
            leg_swing = 45
            knee_bend = 55
            arm_swing = 35
            elbow_bend = 25
            hand_swing = 20

            frame["hip"] = {"y": round(hip_bob, 2), "x": round(body_lean * 0.3, 2)}
            frame["spine"] = {"skZ": round(body_lean, 2), "y": round(hip_bob * 0.3, 2)}
            frame["head"] = {"skZ": round(-body_lean * 0.6, 2)}

            l_leg = math.sin(phase) * leg_swing
            l_scale = 1.0 + max(0, math.sin(phase)) * 0.06
            r_scale = 1.0 + max(0, -math.sin(phase)) * 0.06
            frame["left_upper_leg"] = {"skZ": round(l_leg, 2), "scY": round(l_scale, 3)}
            frame["left_lower_leg"] = {"skZ": round(max(0, math.sin(phase)) * knee_bend, 2)}
            frame["right_upper_leg"] = {"skZ": round(-l_leg, 2), "scY": round(r_scale, 3)}
            frame["right_lower_leg"] = {"skZ": round(max(0, -math.sin(phase)) * knee_bend, 2)}

            l_arm = math.sin(phase + math.pi) * arm_swing
            frame["left_upper_arm"] = {"skZ": round(l_arm, 2)}
            frame["left_lower_arm"] = {"skZ": round(max(0, math.sin(phase + math.pi)) * elbow_bend, 2)}
            frame["right_upper_arm"] = {"skZ": round(-l_arm, 2)}
            frame["right_lower_arm"] = {"skZ": round(max(0, -math.sin(phase + math.pi)) * elbow_bend, 2)}
            frame["left_hand"] = {"skZ": round(math.sin(phase + math.pi) * hand_swing, 2)}
            frame["right_hand"] = {"skZ": round(-math.sin(phase + math.pi) * hand_swing, 2)}

        elif direction == "left":
            hip_bob = math.sin(phase * 2) * 12
            body_lean = -math.sin(phase) * 8
            leg_swing = 45
            knee_bend = 55
            arm_swing = 35
            elbow_bend = 25
            hand_swing = 20

            frame["hip"] = {"y": round(hip_bob, 2), "x": round(body_lean * 0.3, 2)}
            frame["spine"] = {"skZ": round(body_lean, 2), "y": round(hip_bob * 0.3, 2)}
            frame["head"] = {"skZ": round(-body_lean * 0.6, 2)}

            l_leg = math.sin(phase) * leg_swing
            l_scale = 1.0 + max(0, math.sin(phase)) * 0.06
            r_scale = 1.0 + max(0, -math.sin(phase)) * 0.06
            frame["left_upper_leg"] = {"skZ": round(l_leg, 2), "scY": round(l_scale, 3)}
            frame["left_lower_leg"] = {"skZ": round(max(0, math.sin(phase)) * knee_bend, 2)}
            frame["right_upper_leg"] = {"skZ": round(-l_leg, 2), "scY": round(r_scale, 3)}
            frame["right_lower_leg"] = {"skZ": round(max(0, -math.sin(phase)) * knee_bend, 2)}

            l_arm = math.sin(phase + math.pi) * arm_swing
            frame["left_upper_arm"] = {"skZ": round(l_arm, 2)}
            frame["left_lower_arm"] = {"skZ": round(max(0, math.sin(phase + math.pi)) * elbow_bend, 2)}
            frame["right_upper_arm"] = {"skZ": round(-l_arm, 2)}
            frame["right_lower_arm"] = {"skZ": round(max(0, -math.sin(phase + math.pi)) * elbow_bend, 2)}
            frame["left_hand"] = {"skZ": round(math.sin(phase + math.pi) * hand_swing, 2)}
            frame["right_hand"] = {"skZ": round(-math.sin(phase + math.pi) * hand_swing, 2)}

        frames.append(frame)

    return frames


# ── Sprite Sheet Generator (image-based skeletal animation) ────────

def rotate_image(img, angle_deg, center):
    """Rotate image around a center point, preserving alpha."""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2
    rotated = cv2.warpAffine(img, M, (new_w, new_h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0, 0))
    # Calculate offset
    dx = (new_w - w) / 2
    dy = (new_h - h) / 2
    return rotated, dx, dy


def segment_body_parts(img_rgba, parts):
    """Extract body part images from the character using bounding boxes.

    Returns dict of {part_name: (part_image, x, y, w, h)}.
    """
    segments = {}
    for part_name, (px, py, pw, ph) in parts.items():
        # Clamp to image bounds
        px = max(0, px)
        py = max(0, py)
        pw = min(pw, img_rgba.shape[1] - px)
        ph = min(ph, img_rgba.shape[0] - py)
        if pw <= 0 or ph <= 0:
            continue
        part_img = img_rgba[py:py+ph, px:px+pw].copy()
        segments[part_name] = (part_img, px, py, pw, ph)
    return segments


def render_frame(segments, parts, bones, frame_data, canvas_w, canvas_h):
    """Render a single animation frame by rotating body parts.

    Draws body parts in back-to-front order, applying joint rotations.
    """
    canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    # Build bone position lookup
    bone_pos = {}
    for b in bones:
        tx = b["transform"]["x"] + canvas_w / 2
        ty = -b["transform"]["y"] + canvas_h / 2
        bone_pos[b["name"]] = (tx, ty)

    # Hip offset (applies to everything)
    hip_offset_y = frame_data.get("hip", {}).get("y", 0)
    hip_offset_x = frame_data.get("hip", {}).get("x", 0)

    # Spine transform
    spine_rot = frame_data.get("spine", {}).get("skZ", 0)
    spine_dy = frame_data.get("spine", {}).get("y", 0)

    # Head transform
    head_rot = frame_data.get("head", {}).get("skZ", 0)

    # Draw order (back to front):
    # 1. Back arm (left_arm for right-facing, right_arm for left-facing)
    # 2. Back leg
    # 3. Torso
    # 4. Head
    # 5. Front leg
    # 6. Front arm

    def paste_part(part_name, rotation=0, offset_x=0, offset_y=0):
        """Paste a body part onto canvas with optional rotation."""
        if part_name not in segments:
            return
        part_img, orig_x, orig_y, pw, ph = segments[part_name]

        # Apply hip offset + part-specific offset
        dest_x = int(orig_x + offset_x + hip_offset_x)
        dest_y = int(orig_y + offset_y + hip_offset_y + spine_dy)

        if abs(rotation) > 0.5:
            # Rotate around the top-center of the part (joint anchor)
            center = (pw / 2, 0)
            rotated, rdx, rdy = rotate_image(part_img, rotation, center)
            rh, rw = rotated.shape[:2]

            # Adjust position for rotation expansion
            dest_x = int(dest_x - (rw - pw) / 2)
            dest_y = int(dest_y)

            # Paste with alpha blending
            paste_onto(canvas, rotated, dest_x, dest_y)
        else:
            paste_onto(canvas, part_img, dest_x, dest_y)

    def paste_part_around_joint(part_name, joint_x, joint_y, rotation):
        """Paste a body part, rotating it around a specific joint point."""
        if part_name not in segments:
            return
        part_img, orig_x, orig_y, pw, ph = segments[part_name]

        # Joint position relative to part's top-left
        rel_jx = joint_x - orig_x
        rel_jy = joint_y - orig_y

        if abs(rotation) > 0.5:
            center = (float(rel_jx), float(rel_jy))
            rotated, rdx, rdy = rotate_image(part_img, rotation, center)
            rh, rw = rotated.shape[:2]
            dest_x = int(orig_x + hip_offset_x - rdx)
            dest_y = int(orig_y + hip_offset_y + spine_dy - rdy)
            paste_onto(canvas, rotated, dest_x, dest_y)
        else:
            dest_x = int(orig_x + hip_offset_x)
            dest_y = int(orig_y + hip_offset_y + spine_dy)
            paste_onto(canvas, part_img, dest_x, dest_y)

    # Get joint positions (pixel coords)
    torso = parts["torso"]
    spine_joint = (torso[0] + torso[2] // 2, torso[1] + int(torso[3] * 0.15))  # shoulder area
    hip_joint = (torso[0] + torso[2] // 2, torso[1] + torso[3])  # bottom of torso

    # ── Draw back parts first ──
    # Back arm
    paste_part_around_joint("left_arm", spine_joint[0], spine_joint[1],
                            frame_data.get("left_upper_arm", {}).get("skZ", 0) + spine_rot)

    # Back leg
    paste_part_around_joint("left_leg", hip_joint[0], hip_joint[1],
                            frame_data.get("left_upper_leg", {}).get("skZ", 0))

    # ── Torso (center) ──
    paste_part("torso", rotation=spine_rot)

    # ── Head ──
    head_joint = (torso[0] + torso[2] // 2, torso[1])
    paste_part_around_joint("head", head_joint[0], head_joint[1], head_rot + spine_rot)

    # ── Draw front parts ──
    # Front leg
    paste_part_around_joint("right_leg", hip_joint[0], hip_joint[1],
                            frame_data.get("right_upper_leg", {}).get("skZ", 0))

    # Front arm
    paste_part_around_joint("right_arm", spine_joint[0], spine_joint[1],
                            frame_data.get("right_upper_arm", {}).get("skZ", 0) + spine_rot)

    return canvas


def paste_onto(canvas, part, x, y):
    """Alpha-composite a part onto canvas at (x, y)."""
    ch, cw = canvas.shape[:2]
    ph, pw = part.shape[:2]

    # Clip to canvas bounds
    src_x1 = max(0, -x)
    src_y1 = max(0, -y)
    src_x2 = min(pw, cw - x)
    src_y2 = min(ph, ch - y)
    dst_x1 = max(0, x)
    dst_y1 = max(0, y)
    dst_x2 = dst_x1 + (src_x2 - src_x1)
    dst_y2 = dst_y1 + (src_y2 - src_y1)

    if src_x2 <= src_x1 or src_y2 <= src_y1:
        return

    src_region = part[src_y1:src_y2, src_x1:src_x2]
    dst_region = canvas[dst_y1:dst_y2, dst_x1:dst_x2]

    if src_region.shape[2] == 4:
        src_alpha = src_region[:, :, 3:4].astype(np.float32) / 255
        dst_alpha = dst_region[:, :, 3:4].astype(np.float32) / 255

        # Composite: out = src * src_a + dst * (1 - src_a)
        out_rgb = (src_region[:, :, :3].astype(np.float32) * src_alpha +
                   dst_region[:, :, :3].astype(np.float32) * (1 - src_alpha))
        out_alpha = np.maximum(src_alpha, dst_alpha) * 255

        canvas[dst_y1:dst_y2, dst_x1:dst_x2, :3] = out_rgb.astype(np.uint8)
        canvas[dst_y1:dst_y2, dst_x1:dst_x2, 3] = out_alpha.astype(np.uint8).squeeze()
    elif src_region.shape[2] == 3:
        # Source has no alpha, just overwrite RGB
        canvas[dst_y1:dst_y2, dst_x1:dst_x2, :3] = src_region
        canvas[dst_y1:dst_y2, dst_x1:dst_x2, 3] = 255


def generate_sprite_sheet(img_path, parts, bones, walk_frames, direction, out_path, frame_w=64, frame_h=128):
    """Generate a walk cycle sprite sheet PNG from skeleton animation.

    Renders each frame by rotating body parts around joints, then
    assembles into a horizontal sprite sheet.
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False
    h, w = img.shape[:2]

    # Segment body parts
    segments = segment_body_parts(img, parts)

    num_frames = len(walk_frames)
    sheet = np.zeros((frame_h, frame_w * num_frames, 4), dtype=np.uint8)

    for fi, frame_data in enumerate(walk_frames):
        frame = render_frame(segments, parts, bones, frame_data, w, h)

        # Crop to frame size (center the character)
        cx, cy = w // 2, h // 2
        x1 = cx - frame_w // 2
        y1 = cy - frame_h // 2
        x2 = x1 + frame_w
        y2 = y1 + frame_h

        # Clamp
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        cropped = frame[y1:y2, x1:x2]
        ch, cw = cropped.shape[:2]

        # Center in frame
        fx = (frame_w - cw) // 2
        fy = (frame_h - ch) // 2
        sheet[fy:fy+ch, fx+fi*frame_w:fx+fi*frame_w+cw] = cropped

    cv2.imwrite(str(out_path), sheet)
    return True


# ── DragonBones JSON Export ────────────────────────────────────────

def export_dragonbones(skeleton_bones, walk_frames, img_path, out_dir):
    """Export DragonBones-compatible JSON + texture atlas."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = out_dir.name

    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"  ⚠️ Cannot load {img_path}")
        return False
    h, w = img.shape[:2]

    db_bones = []
    for b in skeleton_bones:
        db_bones.append({
            "name": b["name"],
            "parent": b["parent"],
            "length": b["length"],
            "transform": b["transform"]
        })

    num_frames = len(walk_frames)
    bone_timelines = []
    for bone in skeleton_bones:
        bname = bone["name"]
        timeline = {"bone": bname, "scale": 1, "offset": 0, "keyframes": []}
        for fi, frame_data in enumerate(walk_frames):
            if bname in frame_data:
                fd = frame_data[bname]
                kf = {
                    "duration": 1,
                    "tweenEasing": 0,
                    "transform": {
                        "x": fd.get("x", 0),
                        "y": fd.get("y", 0),
                        "skX": fd.get("skX", fd.get("skZ", 0)),
                        "skY": fd.get("skY", fd.get("skZ", 0)),
                        "scX": fd.get("scX", 1),
                        "scY": fd.get("scY", 1)
                    }
                }
                timeline["keyframes"].append(kf)
        if timeline["keyframes"]:
            bone_timelines.append(timeline)

    skeleton_json = {
        "version": "5.7.0",
        "name": name,
        "frameRate": 8,
        "type": "Armature",
        "armature": [{
            "name": name,
            "type": "Armature",
            "bone": db_bones,
            "slot": [{"name": "body", "parent": "spine", "displayIndex": 0,
                      "display": [{"name": name, "type": "image", "path": name}]}],
            "skin": [{"name": "default", "slot": [{"name": "body",
                      "display": [{"name": name, "type": "image", "path": name,
                                   "transform": {"x": 0, "y": 0, "scX": 1, "scY": 1}}]}]}],
            "animation": [{"name": "walk", "duration": num_frames, "playTimes": 0,
                           "scale": 1, "fadeInTime": 0,
                           "bone": bone_timelines, "slot": [], "timeline": []}]
        }]
    }

    ske_path = out_dir / f"{name}_ske.json"
    with open(ske_path, "w") as f:
        json.dump(skeleton_json, f, indent=2, ensure_ascii=False)

    atlas_json = {"name": name, "imagePath": f"{name}.png",
                  "width": w, "height": h,
                  "SubTexture": [{"name": name, "x": 0, "y": 0, "width": w, "height": h}]}
    tex_path = out_dir / f"{name}_tex.json"
    with open(tex_path, "w") as f:
        json.dump(atlas_json, f, indent=2, ensure_ascii=False)

    img_out = out_dir / f"{name}.png"
    cv2.imwrite(str(img_out), img)
    print(f"  ✓ DragonBones: {out_dir}/")
    return True


# ── Batch Processor ────────────────────────────────────────────────

def process_character(char_name, sprites_dir="assets/sprites", output_dir="assets/sprites"):
    """Process all 4 directions for a character, generating rigs + sprite sheets."""
    directions = ["down", "left", "right", "up"]
    results = {}

    for direction in directions:
        cutout_path = os.path.join(sprites_dir, f"cutout_{char_name}_{direction}.png")
        if not os.path.exists(cutout_path):
            print(f"  ⚠️  Skipping {char_name}/{direction}: no cutout image")
            continue

        print(f"\n{'─'*40}")
        print(f"  {char_name} / {direction}")
        print(f"{'─'*40}")

        img = cv2.imread(cutout_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"  ✗ Cannot load {cutout_path}")
            continue
        h, w = img.shape[:2]

        # Detect body parts
        parts = detect_body_parts(img)
        if parts is None:
            print(f"  ✗ No character found")
            continue

        # Build skeleton
        bones = build_skeleton(parts, w, h)

        # Generate direction-specific walk cycle
        walk_frames = generate_walk_cycle_direction(bones, direction)

        # Generate sprite sheet
        sheet_path = os.path.join(output_dir, f"sheet_{char_name}_{direction}.png")
        ok = generate_sprite_sheet(cutout_path, parts, bones, walk_frames, direction, sheet_path)
        if ok:
            print(f"  ✓ Sheet: {sheet_path}")
        else:
            print(f"  ✗ Failed to generate sheet")

        # Also generate DragonBones rig
        rig_dir = os.path.join(output_dir, f"rig_{char_name}_{direction}")
        export_dragonbones(bones, walk_frames, cutout_path, rig_dir)
        print(f"  ✓ Rig: {rig_dir}/")

        # Generate individual frames from the sheet
        sheet_img = cv2.imread(sheet_path, cv2.IMREAD_UNCHANGED)
        if sheet_img is not None:
            fw = sheet_img.shape[1] // 8
            fh = sheet_img.shape[0]
            for fi in range(8):
                frame_img = sheet_img[:, fi*fw:(fi+1)*fw]
                frame_path = os.path.join(output_dir, f"{char_name}_{direction}_f{fi}.png")
                cv2.imwrite(frame_path, frame_img)
            print(f"  ✓ Frames: {char_name}_{direction}_f0..7.png")

        results[direction] = True

    return results


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DragonBones auto-rig + sprite sheet generator")
    parser.add_argument("image", nargs="?", help="Single character image (or use --batch)")
    parser.add_argument("-o", "--output", default="dragonbones_rig", help="Output directory/name")
    parser.add_argument("--preview", action="store_true", help="Generate skeleton preview")
    parser.add_argument("--html", action="store_true", help="Generate HTML animated preview")
    parser.add_argument("--frames", type=int, default=8, help="Walk cycle frames (default: 8)")
    parser.add_argument("--detect-only", action="store_true", help="Only detect body parts")
    parser.add_argument("--batch", action="store_true", help="Process all characters (joker, kai, oracle)")
    parser.add_argument("--sprites-dir", default="assets/sprites", help="Sprites directory")
    args = parser.parse_args()

    print(f"🦴 DragonBones Auto-Rig + Sprite Sheet Generator")
    print(f"{'='*50}")

    if args.batch:
        # Batch mode: process all characters
        chars = ["joker", "kai", "oracle"]
        for char_name in chars:
            print(f"\n{'='*50}")
            print(f"🎬 {char_name.upper()}")
            print(f"{'='*50}")
            process_character(char_name, args.sprites_dir, args.sprites_dir)
        print(f"\n✅ All done!")
        return

    # Single image mode
    if not args.image:
        parser.error("Either provide an image path or use --batch")

    img = cv2.imread(args.image, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"✗ Cannot load {args.image}")
        sys.exit(1)
    h, w = img.shape[:2]
    print(f"  ✓ Source: {args.image} ({w}×{h})")

    print(f"\n📐 Detecting body parts...")
    parts = detect_body_parts(img)
    if parts is None:
        print("  ✗ No character found in image")
        sys.exit(1)

    for name, (px, py, pw, ph) in parts.items():
        print(f"  {name:15s}: ({px:3d},{py:3d}) {pw}×{ph}px")

    if args.detect_only:
        return

    print(f"\n🦴 Building skeleton...")
    bones = build_skeleton(parts, w, h)
    for b in bones:
        parent_info = f" → {b['parent']}" if b['parent'] else ""
        print(f"  {b['name']:20s} len={b['length']:5.1f}{parent_info}")

    # Guess direction from filename
    direction = "down"
    for d in ["down", "left", "right", "up"]:
        if d in args.image.lower():
            direction = d
            break

    print(f"\n🚶 Generating {args.frames}-frame walk cycle (direction: {direction})...")
    walk_frames = generate_walk_cycle_direction(bones, direction)

    print(f"\n📦 Exporting...")
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # DragonBones JSON
    ok = export_dragonbones(bones, walk_frames, args.image, out_dir)
    if ok:
        print(f"  ✓ DragonBones rig exported")

    # Sprite sheet
    sheet_path = out_dir / f"sheet_{direction}.png"
    ok = generate_sprite_sheet(args.image, parts, bones, walk_frames, direction, sheet_path)
    if ok:
        print(f"  ✓ Sprite sheet: {sheet_path}")

    if args.preview:
        generate_preview(args.image, parts, bones, out_dir / "preview_skeleton.png")

    if args.html:
        generate_html_preview(args.image, parts, bones, walk_frames, out_dir / "preview.html")

    print(f"\n✅ Done!")


def generate_preview(img_path, parts, bones, out_path):
    """Generate a visual preview of the detected skeleton overlay."""
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return
    h, w = img.shape[:2]

    # Convert to BGR for drawing
    if img.shape[2] == 4:
        # Alpha composite over black
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        bgr = img[:, :, :3].astype(np.float32) * alpha
        preview = bgr.astype(np.uint8)
    else:
        preview = img.copy()

    # Draw body part bounding boxes
    colors = {
        "head": (0, 255, 0),
        "torso": (255, 0, 0),
        "left_arm": (0, 165, 255),
        "right_arm": (0, 0, 255),
        "left_leg": (255, 255, 0),
        "right_leg": (255, 0, 255),
    }

    for part_name, (px, py, pw, ph) in parts.items():
        color = colors.get(part_name, (128, 128, 128))
        cv2.rectangle(preview, (px, py), (px+pw, py+ph), color, 1)
        cv2.putText(preview, part_name, (px, py-2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    # Draw bone connections
    def get_bone_pos(bone):
        tx = bone["transform"]["x"]
        ty = bone["transform"]["y"]
        px = tx + w / 2
        py = -ty + h / 2
        return int(px), int(py)

    for bone in bones:
        if bone["parent"]:
            parent = next((b for b in bones if b["name"] == bone["parent"]), None)
            if parent:
                p1 = get_bone_pos(parent)
                p2 = get_bone_pos(bone)
                cv2.line(preview, p1, p2, (0, 255, 255), 1)

    # Draw joint circles
    for bone in bones:
        px, py = get_bone_pos(bone)
        cv2.circle(preview, (px, py), 3, (0, 255, 255), -1)

    cv2.imwrite(str(out_path), preview)
    print(f"  ✓ Preview: {out_path}")


# ── HTML Preview (animated) ────────────────────────────────────────

def generate_html_preview(img_path, parts, bones, walk_frames, out_path):
    """Generate an HTML file with animated skeleton preview."""
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    h, w = img.shape[:2]

    # Convert image to base64 data URI
    import base64
    _, buf = cv2.imencode(".png", img)
    img_b64 = base64.b64encode(buf).decode()
    data_uri = f"data:image/png;base64,{img_b64}"

    # Build bone data for JS
    bones_js = []
    for bone in bones:
        tx = bone["transform"]["x"] + w / 2
        ty = -bone["transform"]["y"] + h / 2
        parent_name = bone["parent"]
        bones_js.append({
            "name": bone["name"],
            "parent": parent_name,
            "x": round(tx, 1),
            "y": round(ty, 1),
            "length": bone["length"]
        })

    frames_js = []
    for fi, frame_data in enumerate(walk_frames):
        f = {}
        for bname, transforms in frame_data.items():
            f[bname] = transforms
        frames_js.append(f)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>DragonBones Preview - {Path(img_path).stem}</title>
<style>
  body {{ margin: 0; background: #1a1a2e; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; font-family: monospace; color: #eee; }}
  canvas {{ image-rendering: pixelated; border: 1px solid #333; }}
  .info {{ margin-top: 10px; font-size: 12px; color: #888; }}
  .controls {{ margin-top: 8px; }}
  button {{ background: #333; color: #eee; border: 1px solid #555; padding: 4px 12px; cursor: pointer; font-family: monospace; }}
  button:hover {{ background: #444; }}
</style>
</head>
<body>
<canvas id="c" width="{w*3}" height="{h*3}"></canvas>
<div class="info">Frame: <span id="frame">0</span>/8 | Bones: {len(bones)} | Auto-rigged by dragonbones_rig.py</div>
<div class="controls">
  <button onclick="togglePause()">⏸ Pause</button>
  <button onclick="stepFrame(-1)">◀ Prev</button>
  <button onclick="stepFrame(1)">▶ Next</button>
  <button onclick="toggleSkeleton()">🦴 Toggle Skeleton</button>
</div>
<script>
const W = {w}, H = {h}, SCALE = 3;
const bones = {json.dumps(bones_js)};
const frames = {json.dumps(frames_js)};
const img = new Image();
img.src = "{data_uri}";

let frameIdx = 0;
let paused = false;
let showSkeleton = true;
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");

function drawFrame() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, W, H, 0, 0, W*SCALE, H*SCALE);

  if (!showSkeleton) return;

  const frame = frames[frameIdx % frames.length];

  // Draw bones
  ctx.strokeStyle = "#ffcc00";
  ctx.lineWidth = 2;
  ctx.fillStyle = "#ff4444";

  bones.forEach(b => {{
    let tx = b.x, ty = b.y;
    const transforms = frame[b.name] || {{}};
    const skZ = (transforms.skZ || 0) * Math.PI / 180;
    const dy = (transforms.y || 0);

    // Apply hip offset to all children
    if (b.parent === "hip" || b.parent === "spine" || b.parent === "head") {{
      const hipT = frame["hip"] || {{}};
      ty += (hipT.y || 0) * SCALE;
    }}

    ty += dy * SCALE;
    tx *= SCALE;
    ty *= SCALE;

    // Draw joint
    ctx.beginPath();
    ctx.arc(tx, ty, 4, 0, Math.PI*2);
    ctx.fill();

    // Draw bone line to parent
    const parent = bones.find(p => p.name === b.parent);
    if (parent) {{
      let px = parent.x * SCALE, py = parent.y * SCALE;
      const parentT = frame[parent.name] || {{}};
      if (parent.parent === "hip" || parent.parent === "spine") {{
        const hipT = frame["hip"] || {{}};
        py += (hipT.y || 0) * SCALE;
      }}
      py += (parentT.y || 0) * SCALE;
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(tx, ty);
      ctx.stroke();
    }}
  }});

  // Frame number
  ctx.fillStyle = "#ffcc00";
  ctx.font = "14px monospace";
  ctx.fillText("Frame " + frameIdx, 10, H*SCALE - 10);
}}

function animate() {{
  drawFrame();
  if (!paused) {{
    frameIdx = (frameIdx + 1) % 8;
  }}
  setTimeout(animate, 150);
}}

function togglePause() {{ paused = !paused; }}
function stepFrame(d) {{ frameIdx = (frameIdx + d + 8) % 8; drawFrame(); }}
function toggleSkeleton() {{ showSkeleton = !showSkeleton; drawFrame(); }}

img.onload = () => animate();
</script>
</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(html)
    print(f"  ✓ HTML Preview: {out_path}")


if __name__ == "__main__":
    main()

