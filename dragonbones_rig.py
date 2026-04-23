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

    Uses alpha channel + vertical/horizontal projection to find:
    head, torso, left_arm, right_arm, left_leg, right_leg

    Returns dict of {part: (x, y, w, h)} in pixel coords.
    """
    h, w = img_rgba.shape[:2]
    alpha = img_rgba[:, :, 3] if img_rgba.shape[2] == 4 else np.ones((h, w), dtype=np.uint8) * 255

    # Binary mask of character
    mask = (alpha > 30).astype(np.uint8)

    # Find character bounding box
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None

    char_x1, char_x2 = xs.min(), xs.max()
    char_y1, char_y2 = ys.min(), ys.max()
    char_w = char_x2 - char_x1
    char_h = char_y2 - char_y1

    # Vertical projection (how many pixels per row)
    v_proj = mask.sum(axis=1).astype(np.float32)
    # Horizontal projection (how many pixels per column)
    h_proj = mask.sum(axis=0).astype(np.float32)

    # ── Find head region ──
    # Head is the top region with consistent width, separated by a narrow neck
    head_top = char_y1
    # Find where the character starts narrowing (neck)
    head_bottom = char_y1
    max_width_at_top = 0
    for y in range(char_y1, char_y1 + int(char_h * 0.5)):
        row_width = int(v_proj[y])
        if row_width > max_width_at_top * 0.7:
            max_width_at_top = max(max_width_at_top, row_width)
            head_bottom = y
        elif row_width < max_width_at_top * 0.5:
            break

    head_h = head_bottom - head_top
    if head_h < char_h * 0.15:
        head_h = int(char_h * 0.28)
        head_bottom = head_top + head_h

    # Head width: find the widest row in head region
    head_region = mask[head_top:head_bottom, :]
    head_h_proj = head_region.sum(axis=0)
    head_xs = np.where(head_h_proj > 0)[0]
    if len(head_xs) > 0:
        head_x1, head_x2 = head_xs.min(), head_xs.max()
    else:
        head_x1 = char_x1 + int(char_w * 0.25)
        head_x2 = char_x2 - int(char_w * 0.25)

    head_w = head_x2 - head_x1
    head_cx = (head_x1 + head_x2) // 2

    # ── Find torso region ──
    torso_top = head_bottom
    torso_bottom = torso_top + int(char_h * 0.3)
    if torso_bottom > char_y2:
        torso_bottom = char_y2

    # Torso width from projection
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

    # ── Find leg region ──
    legs_top = torso_bottom
    legs_bottom = char_y2
    legs_h = legs_bottom - legs_top

    # Split legs by finding the gap between them
    leg_region = mask[legs_top:legs_bottom, :]
    leg_h_proj = leg_region.sum(axis=0)

    # Find center gap (where legs separate)
    center_x = torso_cx
    gap_search_range = int(torso_w * 0.3)
    left_leg_x2 = center_x - 2
    right_leg_x1 = center_x + 2

    # Look for minimum in horizontal projection near center
    center_start = max(0, center_x - gap_search_range)
    center_end = min(w, center_x + gap_search_range)
    center_profile = leg_h_proj[center_start:center_end]
    if len(center_profile) > 4:
        # Smooth and find minimum
        kernel = np.ones(3) / 3
        smoothed = np.convolve(center_profile, kernel, mode='same')
        min_idx = np.argmin(smoothed)
        gap_x = center_start + min_idx
        left_leg_x2 = gap_x - 1
        right_leg_x1 = gap_x + 1

    # Left leg bounding box
    left_leg_mask = leg_region[:, :left_leg_x2]
    lxs = np.where(left_leg_mask.sum(axis=0) > 0)[0]
    left_leg_x1 = lxs.min() if len(lxs) > 0 else torso_x1

    # Right leg bounding box
    right_leg_mask = leg_region[:, right_leg_x1:]
    rxs = np.where(right_leg_mask.sum(axis=0) > 0)[0]
    right_leg_x2 = (right_leg_x1 + rxs.max()) if len(rxs) > 0 else torso_x2

    # ── Find arm regions ──
    arm_top = torso_top + int((torso_bottom - torso_top) * 0.1)
    arm_bottom = torso_top + int((torso_bottom - torso_top) * 0.9)

    arm_region = mask[arm_top:arm_bottom, :]
    arm_v_proj = arm_region.sum(axis=1)

    # Left arm: find leftmost pixels in torso-upper region
    left_arm_x1 = max(0, torso_x1 - int(torso_w * 0.5))
    left_arm_x2 = torso_x1 + int(torso_w * 0.15)

    # Right arm: find rightmost pixels
    right_arm_x1 = torso_x2 - int(torso_w * 0.15)
    right_arm_x2 = min(w, torso_x2 + int(torso_w * 0.5))

    # Check if arms exist (have pixels)
    left_arm_region = mask[arm_top:arm_bottom, left_arm_x1:left_arm_x2]
    right_arm_region = mask[arm_top:arm_bottom, right_arm_x1:right_arm_x2]

    if left_arm_region.sum() < 10:
        left_arm_x1 = torso_x1
        left_arm_x2 = torso_x1 + int(torso_w * 0.1)
    if right_arm_region.sum() < 10:
        right_arm_x1 = torso_x2 - int(torso_w * 0.1)
        right_arm_x2 = torso_x2

    parts = {
        "head":     (head_x1, head_top, head_x2 - head_x1, head_bottom - head_top),
        "torso":    (torso_x1, torso_top, torso_x2 - torso_x1, torso_bottom - torso_top),
        "left_arm": (left_arm_x1, arm_top, left_arm_x2 - left_arm_x1, arm_bottom - arm_top),
        "right_arm":(right_arm_x1, arm_top, right_arm_x2 - right_arm_x1, arm_bottom - arm_top),
        "left_leg": (left_leg_x1, legs_top, left_leg_x2 - left_leg_x1, legs_bottom - legs_top),
        "right_leg":(right_leg_x1, legs_top, right_leg_x2 - right_leg_x1, legs_bottom - legs_top),
    }

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


# ── DragonBones JSON Export ────────────────────────────────────────

def export_dragonbones(skeleton_bones, walk_frames, img_path, out_dir):
    """Export DragonBones-compatible JSON + texture atlas.

    Output files:
        {out_dir}_ske.json  — skeleton + animation data
        {out_dir}_tex.json  — texture atlas
        {out_dir}.png       — sprite sheet (if source is single image)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = out_dir.name

    # Load source image
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"✗ Cannot load {img_path}")
        return False
    h, w = img.shape[:2]

    # ── Build skeleton JSON ──
    db_bones = []
    for b in skeleton_bones:
        db_bones.append({
            "name": b["name"],
            "parent": b["parent"],
            "length": b["length"],
            "transform": b["transform"]
        })

    # ── Build animation keyframes ──
    num_frames = len(walk_frames)

    # For each bone, create timeline with keyframes
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

    # ── Build slot timeline (image display) ──
    # For simplicity, show the same image in all frames
    # In a full rig, each frame would reference different mesh deformations
    slot_timelines = [{
        "slot": "body",
        "keyframes": [{
            "duration": 1,
            "displayIndex": 0,
            "tweenEasing": 0
        }] * num_frames
    }]

    skeleton_json = {
        "version": "5.7.0",
        "name": name,
        "frameRate": 8,
        "type": "Armature",
        "userData": {
            "generator": "dragonbones_rig.py (auto-rig)",
            "source_image": str(img_path)
        },
        "armature": [{
            "name": name,
            "type": "Armature",
            "bone": db_bones,
            "slot": [{
                "name": "body",
                "parent": "spine",
                "displayIndex": 0,
                "display": [{
                    "name": name,
                    "type": "image",
                    "path": name
                }]
            }],
            "skin": [{
                "name": "default",
                "slot": [{
                    "name": "body",
                    "display": [{
                        "name": name,
                        "type": "image",
                        "path": name,
                        "transform": {
                            "x": 0,
                            "y": 0,
                            "scX": 1,
                            "scY": 1
                        }
                    }]
                }]
            }],
            "animation": [{
                "name": "walk",
                "duration": num_frames,
                "playTimes": 0,
                "scale": 1,
                "fadeInTime": 0,
                "bone": bone_timelines,
                "slot": slot_timelines,
                "timeline": []
            }]
        }]
    }

    # Save skeleton JSON
    ske_path = out_dir / f"{name}_ske.json"
    with open(ske_path, "w") as f:
        json.dump(skeleton_json, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Skeleton: {ske_path}")

    # ── Build texture atlas ──
    atlas_json = {
        "name": name,
        "imagePath": f"{name}.png",
        "width": w,
        "height": h,
        "SubTexture": [{
            "name": name,
            "x": 0,
            "y": 0,
            "width": w,
            "height": h
        }]
    }

    tex_path = out_dir / f"{name}_tex.json"
    with open(tex_path, "w") as f:
        json.dump(atlas_json, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Atlas: {tex_path}")

    # Copy source image
    img_out = out_dir / f"{name}.png"
    cv2.imwrite(str(img_out), img)
    print(f"  ✓ Image: {img_out}")

    return True


# ── Visual Preview ─────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto-rig front-facing character for DragonBones")
    parser.add_argument("image", help="Source character image (front-facing, RGBA preferred)")
    parser.add_argument("-o", "--output", default="dragonbones_rig", help="Output directory name")
    parser.add_argument("--preview", action="store_true", help="Generate visual preview images")
    parser.add_argument("--html", action="store_true", help="Generate HTML animated preview")
    parser.add_argument("--frames", type=int, default=8, help="Walk cycle frames (default: 8)")
    parser.add_argument("--detect-only", action="store_true", help="Only detect body parts, no export")
    args = parser.parse_args()

    print(f"🦴 DragonBones Auto-Rig")
    print(f"{'='*40}")

    # Load image
    img = cv2.imread(args.image, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"✗ Cannot load {args.image}")
        sys.exit(1)
    h, w = img.shape[:2]
    print(f"  ✓ Source: {args.image} ({w}×{h})")

    # Detect body parts
    print(f"\n📐 Detecting body parts...")
    parts = detect_body_parts(img)
    if parts is None:
        print("  ✗ No character found in image")
        sys.exit(1)

    for name, (px, py, pw, ph) in parts.items():
        print(f"  {name:15s}: ({px:3d},{py:3d}) {pw}×{ph}px")

    if args.detect_only:
        return

    # Build skeleton
    print(f"\n🦴 Building skeleton...")
    bones = build_skeleton(parts, w, h)
    for b in bones:
        parent_info = f" → {b['parent']}" if b['parent'] else ""
        print(f"  {b['name']:20s} len={b['length']:5.1f}{parent_info}")

    # Generate walk cycle
    print(f"\n🚶 Generating {args.frames}-frame walk cycle...")
    walk_frames = generate_walk_cycle(bones, args.frames)
    print(f"  ✓ {len(walk_frames)} frames generated")

    # Export DragonBones
    print(f"\n📦 Exporting DragonBones...")
    out_dir = Path(args.output)
    ok = export_dragonbones(bones, walk_frames, args.image, out_dir)
    if not ok:
        sys.exit(1)

    # Generate previews
    if args.preview:
        print(f"\n🎨 Generating previews...")
        generate_preview(args.image, parts, bones, out_dir / "preview_skeleton.png")

    if args.html:
        print(f"\n🌐 Generating HTML preview...")
        generate_html_preview(args.image, parts, bones, walk_frames, out_dir / "preview.html")

    print(f"\n{'='*40}")
    print(f"✅ Done! Output: {out_dir}/")
    print(f"   Files: {out_dir.name}_ske.json, {out_dir.name}_tex.json, {out_dir.name}.png")
    print(f"   Import into DragonBones Pro or load with DragonBones runtime.")


if __name__ == "__main__":
    main()
