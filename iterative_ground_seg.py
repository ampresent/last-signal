#!/usr/bin/env python3
"""
Iterative Ground Segmentation — Point-based MobileSAM + OMNI validation.

Workflow per scene:
  1. OMNI identifies 4 seed points on the ground surface
  2. MobileSAM segments around each point (point prompt mode)
  3. Each segment gets a numbered label overlay
  4. OMNI evaluates each segment: matches ground? keep/discard
  5. If OMNI detects uncovered ground → add new seed points
  6. Repeat for 2-3 rounds
  7. Final composite mask = union of all kept segments
  8. Generate PDF report documenting every step
"""

import cv2
import numpy as np
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import onnxruntime as ort

# ── Constants ──
IMG_W, IMG_H = 940, 627
GAME_W, GAME_H = 960, 640
MOBILESAM_SIZE = 1024
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MASK_DIR = os.path.join(ASSETS_DIR, "masks")
MODELS_DIR = os.path.join(BASE_DIR, "models")
WORK_DIR = os.path.join(BASE_DIR, "ground_seg_work")

ENCODER_PATH = os.path.join(MODELS_DIR, "mobilesam.encoder.onnx")
DECODER_PATH = os.path.join(MODELS_DIR, "mobile_sam.onnx")
MIMO_API_SCRIPT = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")

# Colors for segment labels
SEGMENT_COLORS = [
    (255, 80, 80),    # Red
    (80, 200, 255),   # Cyan
    (255, 200, 40),   # Yellow
    (120, 255, 120),  # Green
    (255, 120, 255),  # Magenta
    (255, 160, 80),   # Orange
    (120, 120, 255),  # Blue
    (200, 255, 120),  # Lime
]

os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(MASK_DIR, exist_ok=True)


# ════════════════════════════════════════════════
# MobileSAM — point prompt mode
# ════════════════════════════════════════════════

class MobileSAM:
    """MobileSAM ONNX with point-prompt support."""

    def __init__(self):
        for p, n in [(ENCODER_PATH, "encoder"), (DECODER_PATH, "decoder")]:
            if not os.path.isfile(p):
                raise FileNotFoundError(f"MobileSAM {n} not found: {p}")

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2

        self.encoder = ort.InferenceSession(ENCODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(DECODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        print("  ✓ MobileSAM loaded")

    def _preprocess(self, img_bgr):
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]
        scale = MOBILESAM_SIZE / max(orig_h, orig_w)
        new_h, new_w = int(orig_h * scale), int(orig_w * scale)
        resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        padded = np.zeros((MOBILESAM_SIZE, MOBILESAM_SIZE, 3), dtype=np.uint8)
        padded[:new_h, :new_w, :] = resized
        normalized = (padded.astype(np.float32) / 255.0 - MEAN) / STD
        return normalized, scale, (orig_h, orig_w)

    def _encode(self, input_hwc):
        return self.encoder.run(None, {"input_image": input_hwc})[0]

    def _decode_point(self, image_embeddings, scale, orig_size, points, labels):
        """Decode with point prompts. points: [(x,y), ...], labels: [1=fg, 0=bg, ...]"""
        orig_h, orig_w = orig_size
        point_coords = np.array([[[p[0]*scale, p[1]*scale] for p in points]], dtype=np.float32)
        point_labels = np.array([labels], dtype=np.float32)
        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask = np.array([0], dtype=np.float32)
        orig_im_size = np.array([orig_h, orig_w], dtype=np.float32)

        outputs = self.decoder.run(None, {
            "image_embeddings": image_embeddings,
            "point_coords": point_coords,
            "point_labels": point_labels,
            "mask_input": mask_input,
            "has_mask_input": has_mask,
            "orig_im_size": orig_im_size,
        })

        masks = outputs[0]
        iou_preds = outputs[1]
        best_idx = np.argmax(iou_preds[0])
        mask_logits = masks[0, best_idx]
        mask_prob = 1.0 / (1.0 + np.exp(-np.clip(mask_logits, -50, 50)))
        mask_resized = cv2.resize(mask_prob, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        binary = (mask_resized > 0.5).astype(np.uint8) * 255

        # Morphological cleanup
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
        return binary, float(iou_preds[0][best_idx])

    def _decode_bbox(self, image_embeddings, scale, orig_size, bbox):
        """Decode with bbox prompt (fallback)."""
        orig_h, orig_w = orig_size
        x1, y1, x2, y2 = bbox
        point_coords = np.array([[[x1*scale, y1*scale], [x2*scale, y2*scale]]], dtype=np.float32)
        point_labels = np.array([[2, 3]], dtype=np.float32)
        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask = np.array([0], dtype=np.float32)
        orig_im_size = np.array([orig_h, orig_w], dtype=np.float32)

        outputs = self.decoder.run(None, {
            "image_embeddings": image_embeddings,
            "point_coords": point_coords,
            "point_labels": point_labels,
            "mask_input": mask_input,
            "has_mask_input": has_mask,
            "orig_im_size": orig_im_size,
        })

        masks = outputs[0]
        iou_preds = outputs[1]
        best_idx = np.argmax(iou_preds[0])
        mask_logits = masks[0, best_idx]
        mask_prob = 1.0 / (1.0 + np.exp(-np.clip(mask_logits, -50, 50)))
        mask_resized = cv2.resize(mask_prob, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        binary = (mask_resized > 0.5).astype(np.uint8) * 255
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
        return binary, float(iou_preds[0][best_idx])

    def segment_at_point(self, img_bgr, point, expand_px=120):
        """Segment around a single point using bbox constraint. Returns (mask, iou)."""
        input_hwc, scale, orig_size = self._preprocess(img_bgr)
        embeddings = self._encode(input_hwc)

        h, w = orig_size
        x, y = point

        # Clamp point to image bounds
        x = max(5, min(x, w - 5))
        y = max(5, min(y, h - 5))

        # Use a generous bbox centered on the point, biased downward for ground
        left = max(0, x - expand_px)
        right = min(w, x + expand_px)
        top = max(0, y - int(expand_px * 0.6))
        bottom = min(h, y + int(expand_px * 1.2))
        bbox = [left, top, right, bottom]

        mask, iou = self._decode_bbox(embeddings, scale, orig_size, bbox)

        # If mask is nearly empty, try even larger bbox
        area_ratio = np.count_nonzero(mask) / (mask.shape[0] * mask.shape[1])
        if area_ratio < 0.005:
            expand2 = int(expand_px * 2.5)
            bbox2 = [max(0, x-expand2), max(0, y-int(expand2*0.6)),
                     min(w, x+expand2), min(h, y+int(expand2*1.2))]
            mask2, iou2 = self._decode_bbox(embeddings, scale, orig_size, bbox2)
            area2 = np.count_nonzero(mask2) / (mask2.shape[0] * mask2.shape[1])
            if area2 > area_ratio:
                return mask2, iou2

        return mask, iou


# ════════════════════════════════════════════════
# OMNI (mimo-omni) helpers
# ════════════════════════════════════════════════

def omni_analyze(image_path, prompt, max_tokens=4096):
    """Call mimo-omni to analyze an image."""
    result = subprocess.run(
        ["bash", MIMO_API_SCRIPT, "image", image_path, prompt,
         "--max-tokens", str(max_tokens)],
        capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(f"OMNI failed: {result.stderr[:300]}")
    return result.stdout.strip()


def omni_identify_ground_points(scene_img_path, scene_id, img_w, img_h):
    """Ask OMNI to identify 4 small points on the ground/road surface."""
    prompt = (
        f"This is a 2D adventure game scene background ({img_w}x{img_h} pixels). "
        f"Scene: {scene_id}\n\n"
        "I need you to identify exactly 4 points that are clearly on the GROUND/ROAD surface "
        "(not on walls, furniture, obstacles, or decorations). "
        "Choose points that are spread across different areas of the ground to get good coverage.\n\n"
        "Return ONLY a JSON array (no other text):\n"
        "[{\"x\": <pixel_x>, \"y\": <pixel_y>, \"desc\": \"brief description of this point's location\"}]\n\n"
        "Rules:\n"
        "- Points MUST be on walkable ground/road/floor surface\n"
        "- Spread points across the ground area (don't cluster them)\n"
        "- Avoid edges of obstacles\n"
        "- y coordinate should be in the lower portion of the image (ground area)"
    )
    response = omni_analyze(scene_img_path, prompt)
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if not json_match:
        raise RuntimeError(f"OMNI didn't return valid JSON: {response[:200]}")

    points_data = json.loads(json_match.group())
    points = []
    max_x = max(int(p.get("x", 0)) for p in points_data)
    max_y = max(int(p.get("y", 0)) for p in points_data)

    # If OMNI returned coordinates for a different resolution (e.g. 960x640), rescale
    scale_x, scale_y = 1.0, 1.0
    if max_x > img_w * 1.1 or max_y > img_h * 1.1:
        # Likely 960x640 game coords, rescale to actual
        scale_x = img_w / 960.0
        scale_y = img_h / 640.0
        print(f"  ⚠️  Rescaling OMNI coords from ~960x640 to {img_w}x{img_h}")

    for p in points_data:
        x = int(int(p["x"]) * scale_x)
        y = int(int(p["y"]) * scale_y)
        x = max(10, min(x, img_w - 10))
        y = max(10, min(y, img_h - 10))
        points.append({"x": x, "y": y, "desc": p.get("desc", "")})

    print(f"  🔍 OMNI identified {len(points)} ground points:")
    for i, p in enumerate(points):
        print(f"     P{i+1}: ({p['x']}, {p['y']}) — {p['desc']}")
    return points


def omni_evaluate_segments(scene_img_path, overlay_path, scene_id, segment_info):
    """Ask OMNI to evaluate which segments are actually ground."""
    prompt = (
        f"This is scene '{scene_id}' (940x627) with numbered colored overlays marking candidate ground areas.\n"
        f"Each numbered region was generated by an AI segmentation model from a seed point on the ground.\n\n"
        "Segments:\n"
    )
    for info in segment_info:
        prompt += f"  - Segment #{info['id']}: {info['color_name']} region near ({info['cx']},{info['cy']})\n"

    prompt += (
        "\nFor EACH segment, judge:\n"
        "1. Does this segment cover ONLY walkable ground/road/floor? (not walls, furniture, obstacles)\n"
        "2. Is the shape reasonable for a ground area?\n\n"
        "Return ONLY a JSON array, nothing else:\n"
        '[{"id": 1, "verdict": "KEEP", "reason": "covers floor only"}, {"id": 2, "verdict": "REMOVE", "reason": "covers wall"}]\n'
        "Use KEEP if segment covers ground only, REMOVE if it includes walls/obstacles/non-ground."
    )
    response = omni_analyze(overlay_path, prompt)

    # Try multiple parsing strategies
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if not json_match:
        # Try to find individual verdicts
        evaluations = []
        for info in segment_info:
            sid = info["id"]
            # Look for patterns like "#1: KEEP" or "Segment 1: KEEP"
            keep_pattern = re.search(rf'(?:seg(?:ment)?\s*#?{sid}|#{sid})[^[]*?(KEEP|REMOVE)', response, re.IGNORECASE)
            if keep_pattern:
                verdict = keep_pattern.group(1).upper()
                evaluations.append({"id": sid, "verdict": verdict, "reason": ""})
        if evaluations:
            return evaluations
        print(f"  ⚠️  OMNI eval parse failed: {response[:200]}")
        return None

    evaluations = json.loads(json_match.group())
    return evaluations


def omni_check_coverage(scene_img_path, current_mask_path, scene_id):
    """Ask OMNI if there are still uncovered ground areas."""
    prompt = (
        f"This is scene '{scene_id}' (940x627 pixels) with a green overlay showing the current walkable ground mask.\n"
        "Green areas = already identified as ground.\n\n"
        "Are there significant ground/road/floor areas that are NOT covered by green?\n"
        "If yes, suggest 2-3 pixel coordinates where uncovered ground exists.\n\n"
        "IMPORTANT: Coordinates must be within 0-940 for x and 0-627 for y.\n\n"
        "Return ONLY JSON:\n"
        '{"has_uncovered": true/false, "suggested_points": [{"x": <0-940>, "y": <0-627>, "desc": "..."}], "reasoning": "..."}'
    )
    response = omni_analyze(current_mask_path, prompt)
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if not json_match:
        return {"has_uncovered": False, "suggested_points": []}
    result = json.loads(json_match.group())
    # Clamp suggested points to image bounds
    for p in result.get("suggested_points", []):
        p["x"] = max(10, min(int(p.get("x", 0)), 930))
        p["y"] = max(10, min(int(p.get("y", 0)), 617))
    return result


# ════════════════════════════════════════════════
# Visualization helpers
# ════════════════════════════════════════════════

def create_labeled_overlay(img_bgr, segments, title=""):
    """Create overlay with numbered colored segments on the scene image."""
    h, w = img_bgr.shape[:2]
    overlay = img_bgr.copy()

    for seg in segments:
        color = SEGMENT_COLORS[(seg["id"] - 1) % len(SEGMENT_COLORS)]
        mask = seg["mask"]
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

        # Semi-transparent color overlay
        color_layer = np.zeros_like(overlay)
        color_layer[mask > 128] = color
        overlay = cv2.addWeighted(overlay, 0.7, color_layer, 0.3, 0)

        # Draw number label at centroid
        ys, xs = np.where(mask > 128)
        if len(xs) > 0:
            cx, cy = int(np.mean(xs)), int(np.mean(ys))
            cv2.putText(overlay, str(seg["id"]), (cx-10, cy+10),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
            cv2.putText(overlay, str(seg["id"]), (cx-10, cy+10),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)

    if title:
        cv2.putText(overlay, title, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    return overlay


def create_green_overlay(img_bgr, mask):
    """Create green overlay for coverage check (alpha=40)."""
    h, w = img_bgr.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = img_bgr.copy()
    green = np.zeros_like(overlay)
    green[mask > 128] = (0, 255, 0)
    blended = cv2.addWeighted(overlay, 0.85, green, 0.15, 0)
    return blended


def save_step_image(img, scene_id, round_num, step_name):
    """Save intermediate image for PDF documentation."""
    fname = f"{scene_id}_r{round_num}_{step_name}.png"
    path = os.path.join(WORK_DIR, fname)
    cv2.imwrite(path, img)
    return path


# ════════════════════════════════════════════════
# Main iterative segmentation
# ════════════════════════════════════════════════

def process_scene(scene_id, scene_img_path, sam, max_rounds=3):
    """Run iterative ground segmentation for one scene."""
    img = cv2.imread(scene_img_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read: {scene_img_path}")

    h, w = img.shape[:2]
    print(f"\n{'='*60}")
    print(f"🎬 Scene: {scene_id} ({w}x{h})")
    print(f"{'='*60}")

    # All step records for PDF
    steps = []
    all_segments = {}  # id -> {"mask": ..., "iou": ..., "status": ...}
    kept_mask = np.zeros((h, w), dtype=np.uint8)
    next_seg_id = 1

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─'*50}")
        print(f"📍 Round {round_num}")
        print(f"{'─'*50}")

        # ── Step A: Identify seed points ──
        if round_num == 1:
            print("  [A] OMNI identifying initial ground points...")
            points = omni_identify_ground_points(scene_img_path, scene_id, w, h)
            step_img = img.copy()
            for i, p in enumerate(points):
                cv2.circle(step_img, (p["x"], p["y"]), 8, (0, 0, 255), -1)
                cv2.circle(step_img, (p["x"], p["y"]), 10, (255, 255, 255), 2)
                cv2.putText(step_img, f"P{i+1}", (p["x"]+12, p["y"]-5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            path = save_step_image(step_img, scene_id, round_num, "seed_points")
            steps.append({"round": round_num, "step": "A", "name": "Seed Points from OMNI",
                         "image": path, "detail": f"OMNI identified {len(points)} ground points"})
        else:
            # Use OMNI-suggested points from coverage check
            print("  [A] OMNI checking for uncovered ground...")
            green_overlay = create_green_overlay(img, kept_mask)
            cov_path = save_step_image(green_overlay, scene_id, round_num, "coverage_check")

            coverage = omni_check_coverage(scene_img_path, cov_path, scene_id)
            steps.append({"round": round_num, "step": "A", "name": "Coverage Check",
                         "image": cov_path,
                         "detail": f"has_uncovered={coverage.get('has_uncovered')}, "
                                   f"suggested={len(coverage.get('suggested_points', []))}"})

            if not coverage.get("has_uncovered"):
                print("  ✅ OMNI says coverage is complete!")
                break

            points = coverage.get("suggested_points", [])
            if not points:
                print("  ⚠️  No new points suggested, stopping.")
                break
            # Limit to 3 new points per round
            points = points[:3]
            print(f"  [A] OMNI suggests {len(points)} new seed points:")
            for i, p in enumerate(points):
                print(f"     P{next_seg_id+i}: ({p['x']}, {p['y']}) — {p.get('desc','')}")

        # ── Step B: Segment each point with MobileSAM ──
        print(f"  [B] MobileSAM segmenting {len(points)} points...")
        round_segments = []
        for p in points:
            x, y = int(p["x"]), int(p["y"])
            mask, iou = sam.segment_at_point(img, (x, y))
            area_pct = np.count_nonzero(mask) / (h * w) * 100

            seg_info = {
                "id": next_seg_id,
                "mask": mask,
                "iou": iou,
                "point": (x, y),
                "area_pct": area_pct,
                "color_name": ["Red","Cyan","Yellow","Green","Magenta","Orange","Blue","Lime"][(next_seg_id-1)%8],
                "status": "pending"
            }
            round_segments.append(seg_info)
            all_segments[next_seg_id] = seg_info

            print(f"     Seg #{next_seg_id}: ({x},{y}) → {area_pct:.1f}% coverage, IoU={iou:.3f}")
            next_seg_id += 1

        # Save individual segment masks
        for seg in round_segments:
            seg_path = os.path.join(WORK_DIR, f"{scene_id}_seg{seg['id']}_mask.png")
            cv2.imwrite(seg_path, seg["mask"])

        # ── Step C: Create labeled overlay ──
        print("  [C] Creating labeled overlay...")
        labeled = create_labeled_overlay(img, round_segments,
                                         title=f"{scene_id} — Round {round_num}")
        labeled_path = save_step_image(labeled, scene_id, round_num, "labeled_overlay")
        steps.append({"round": round_num, "step": "C", "name": "Labeled Segments",
                     "image": labeled_path,
                     "detail": f"{len(round_segments)} segments labeled"})

        # ── Step D: OMNI evaluation ──
        print("  [D] OMNI evaluating segments...")
        seg_info_for_eval = [{"id": s["id"], "color_name": s["color_name"],
                              "cx": s["point"][0], "cy": s["point"][1]}
                             for s in round_segments]

        evaluations = omni_evaluate_segments(scene_img_path, labeled_path,
                                             scene_id, seg_info_for_eval)

        if evaluations:
            for ev in evaluations:
                seg_id = ev.get("id")
                verdict = ev.get("verdict", "REMOVE").upper()
                reason = ev.get("reason", "")
                if seg_id in all_segments:
                    all_segments[seg_id]["status"] = verdict
                    all_segments[seg_id]["reason"] = reason
                    icon = "✅" if verdict == "KEEP" else "❌"
                    print(f"     {icon} Seg #{seg_id}: {verdict} — {reason}")

            # ── Step E: Remove rejected segments ──
            removed = [s for s in round_segments if s["status"] == "REMOVE"]
            kept = [s for s in round_segments if s["status"] == "KEEP"]
            print(f"  [E] Keeping {len(kept)}, removing {len(removed)} segments")

            # Update composite mask with kept segments
            for seg in kept:
                kept_mask = cv2.bitwise_or(kept_mask, seg["mask"])
        else:
            # If OMNI eval fails, keep all segments
            print("  ⚠️  OMNI eval failed, keeping all segments by default")
            for seg in round_segments:
                seg["status"] = "KEEP"
                kept_mask = cv2.bitwise_or(kept_mask, seg["mask"])

        # Save round result
        round_overlay = create_green_overlay(img, kept_mask)
        round_path = save_step_image(round_overlay, scene_id, round_num, "round_result")
        kept_pct = np.count_nonzero(kept_mask) / (h * w) * 100
        steps.append({"round": round_num, "step": "E", "name": "Round Result",
                     "image": round_path,
                     "detail": f"Running coverage: {kept_pct:.1f}%"})

    # ── Final: Morphological cleanup + connectivity ──
    print(f"\n  🧹 Final cleanup...")
    final_mask = cv2.morphologyEx(kept_mask, cv2.MORPH_CLOSE, np.ones((11,11), np.uint8))
    final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

    # Keep largest connected component
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(final_mask)
    if num_labels > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        max_label = np.argmax(areas) + 1
        final_clean = np.zeros_like(final_mask)
        final_clean[labels == max_label] = 255
        final_mask = final_clean

    final_pct = np.count_nonzero(final_mask) / (h * w) * 100
    print(f"  📊 Final coverage: {final_pct:.1f}%")

    # Save final mask at game resolution
    final_game = cv2.resize(final_mask, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
    final_mask_path = os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.png")
    cv2.imwrite(final_mask_path, final_game)

    # Save final overlay
    final_overlay = create_green_overlay(img, final_mask)
    final_overlay_path = save_step_image(final_overlay, scene_id, "final", "final_overlay")

    # Also save as webp for the game
    final_webp_path = os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.webp")
    Image.fromarray(final_game).save(final_webp_path, 'WEBP', quality=90)

    final_overlay_webp = os.path.join(MASK_DIR, f"{scene_id}_walkable_overlay.webp")
    Image.fromarray(cv2.cvtColor(
        cv2.resize(final_overlay, (GAME_W, GAME_H), interpolation=cv2.INTER_LINEAR),
        cv2.COLOR_BGR2RGB)).save(final_overlay_webp, 'WEBP', quality=90)

    steps.append({"round": "final", "step": "F", "name": "Final Walkable Mask",
                 "image": final_overlay_path,
                 "detail": f"Coverage: {final_pct:.1f}%, saved to {final_mask_path}"})

    return {
        "scene_id": scene_id,
        "steps": steps,
        "segments": {k: {"id": v["id"], "point": v["point"], "area_pct": v["area_pct"],
                         "iou": v["iou"], "status": v["status"],
                         "reason": v.get("reason", "")}
                     for k, v in all_segments.items()},
        "final_coverage_pct": final_pct,
        "final_mask_path": final_mask_path,
    }


# ════════════════════════════════════════════════
# PDF Report Generator
# ════════════════════════════════════════════════

def generate_pdf_report(results):
    """Generate a comprehensive PDF report of the entire process."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch, cm
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                         Image as RLImage, Table, TableStyle,
                                         PageBreak, HRFlowable)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        print("  ⚠️  reportlab not installed, generating HTML report instead")
        return generate_html_report(results)

    pdf_path = os.path.join(BASE_DIR, "ground_segmentation_report.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                           leftMargin=1.5*cm, rightMargin=1.5*cm,
                           topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=20, spaceAfter=20)
    heading_style = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=14, spaceAfter=10)
    body_style = ParagraphStyle('Body2', parent=styles['Normal'], fontSize=10, spaceAfter=8)
    caption_style = ParagraphStyle('Caption', parent=styles['Normal'], fontSize=8,
                                   textColor=colors.grey, spaceAfter=12)

    story = []

    # Title page
    story.append(Paragraph("Ground Segmentation Report", title_style))
    story.append(Paragraph("Iterative Point-based MobileSAM + OMNI Validation", styles['Heading3']))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body_style))
    story.append(Paragraph("Scenes: apartment, alley", body_style))
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%"))
    story.append(Spacer(1, 20))

    # Methodology
    story.append(Paragraph("Methodology", heading_style))
    story.append(Paragraph(
        "This report documents an iterative ground segmentation pipeline that combines "
        "OMNI (multimodal vision model) for semantic understanding with MobileSAM for "
        "precise mask generation. The workflow proceeds in rounds:", body_style))
    story.append(Paragraph(
        "<b>1.</b> OMNI identifies seed points on the ground surface<br/>"
        "<b>2.</b> MobileSAM generates segmentation masks from each point<br/>"
        "<b>3.</b> Segments are labeled and overlaid on the scene<br/>"
        "<b>4.</b> OMNI evaluates each segment (KEEP/REMOVE)<br/>"
        "<b>5.</b> Rejected segments are removed<br/>"
        "<b>6.</b> OMNI checks for uncovered ground → new seed points<br/>"
        "<b>7.</b> Repeat until coverage is complete", body_style))
    story.append(PageBreak())

    # Per-scene results
    for result in results:
        scene_id = result["scene_id"]
        story.append(Paragraph(f"Scene: {scene_id}", title_style))

        # Summary table
        seg_data = [["Seg #", "Position", "Area %", "IoU", "Status", "Reason"]]
        for sid, info in result["segments"].items():
            seg_data.append([
                str(info["id"]),
                f"({info['point'][0]}, {info['point'][1]})",
                f"{info['area_pct']:.1f}%",
                f"{info['iou']:.3f}",
                info["status"],
                info.get("reason", "")[:40]
            ])

        t = Table(seg_data, colWidths=[40, 70, 50, 50, 50, 180])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<b>Final coverage: {result['final_coverage_pct']:.1f}%</b>", body_style))
        story.append(Spacer(1, 15))

        # Step images
        for step in result["steps"]:
            story.append(Paragraph(
                f"<b>Round {step['round']} — Step {step['step']}: {step['name']}</b>",
                body_style))
            story.append(Paragraph(step["detail"], caption_style))

            img_path = step["image"]
            if os.path.exists(img_path):
                try:
                    img = Image.open(img_path)
                    iw, ih = img.size
                    # Scale to fit page width (about 17cm)
                    max_w = 17 * cm
                    max_h = 12 * cm
                    scale = min(max_w / iw, max_h / ih)
                    display_w, display_h = iw * scale, ih * scale
                    story.append(RLImage(img_path, width=display_w, height=display_h))
                except Exception as e:
                    story.append(Paragraph(f"[Image error: {e}]", caption_style))
            story.append(Spacer(1, 10))

        story.append(PageBreak())

    # Final summary
    story.append(Paragraph("Summary", title_style))
    summary_data = [["Scene", "Rounds", "Total Segments", "Kept", "Removed", "Final Coverage"]]
    for result in results:
        segs = result["segments"]
        kept = sum(1 for s in segs.values() if s["status"] == "KEEP")
        removed = sum(1 for s in segs.values() if s["status"] == "REMOVE")
        rounds = max(s["round"] for s in result["steps"] if isinstance(s["round"], int))
        summary_data.append([
            result["scene_id"],
            str(rounds),
            str(len(segs)),
            str(kept),
            str(removed),
            f"{result['final_coverage_pct']:.1f}%"
        ])

    t = Table(summary_data, colWidths=[70, 50, 80, 50, 60, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#27ae60')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t)

    doc.build(story)
    print(f"  📄 PDF report: {pdf_path}")
    return pdf_path


def generate_html_report(results):
    """Fallback HTML report if reportlab is not available."""
    html_path = os.path.join(BASE_DIR, "ground_segmentation_report.html")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Ground Segmentation Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #2980b9; margin-top: 30px; }}
.step {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; }}
.step img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin-top: 10px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th {{ background: #2c3e50; color: white; padding: 8px; }}
td {{ border: 1px solid #ddd; padding: 6px; text-align: center; }}
.keep {{ color: #27ae60; font-weight: bold; }}
.remove {{ color: #e74c3c; font-weight: bold; }}
caption {{ font-style: italic; color: #666; text-align: left; margin-bottom: 10px; }}
</style></head><body>
<h1>Ground Segmentation Report</h1>
<p>Iterative Point-based MobileSAM + OMNI Validation</p>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""

    for result in results:
        scene_id = result["scene_id"]
        html += f"<h2>Scene: {scene_id}</h2>\n"
        html += "<table><tr><th>Seg #</th><th>Position</th><th>Area %</th><th>IoU</th><th>Status</th><th>Reason</th></tr>\n"
        for sid, info in result["segments"].items():
            cls = "keep" if info["status"] == "KEEP" else "remove"
            html += f"<tr><td>{info['id']}</td><td>({info['point'][0]},{info['point'][1]})</td>"
            html += f"<td>{info['area_pct']:.1f}%</td><td>{info['iou']:.3f}</td>"
            html += f"<td class='{cls}'>{info['status']}</td><td>{info.get('reason','')}</td></tr>\n"
        html += "</table>\n"
        html += f"<p><b>Final coverage: {result['final_coverage_pct']:.1f}%</b></p>\n"

        for step in result["steps"]:
            html += f"""<div class="step">
<h3>Round {step['round']} — Step {step['step']}: {step['name']}</h3>
<p>{step['detail']}</p>
"""
            if os.path.exists(step["image"]):
                html += f'<img src="{step["image"]}" alt="{step["name"]}">\n'
            html += "</div>\n"

    html += "</body></html>"
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"  📄 HTML report: {html_path}")
    return html_path


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", choices=["apartment", "alley", "all"], default="all")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--pdf-only", action="store_true", help="Only regenerate PDF from existing work")
    args = parser.parse_args()

    print("=" * 60)
    print("🌍 Iterative Ground Segmentation")
    print("   MobileSAM (point prompt) + OMNI validation")
    print("=" * 60)

    scenes = {
        "apartment": os.path.join(ASSETS_DIR, "bg_apartment.webp"),
        "alley": os.path.join(ASSETS_DIR, "bg_alley.webp"),
    }

    if args.scene != "all":
        scenes = {args.scene: scenes[args.scene]}

    # Verify images exist
    for sid, path in scenes.items():
        if not os.path.exists(path):
            print(f"❌ Missing: {path}")
            sys.exit(1)

    if args.pdf_only:
        # Reconstruct from saved work (not implemented, just regenerate)
        print("PDF-only mode requires fresh run. Running full pipeline...")

    # Load MobileSAM
    print("\n🔧 Loading MobileSAM...")
    sam = MobileSAM()

    # Process each scene
    results = []
    for scene_id, img_path in scenes.items():
        result = process_scene(scene_id, img_path, sam, max_rounds=args.max_rounds)
        results.append(result)

    # Generate PDF report
    print(f"\n{'='*60}")
    print("📄 Generating report...")
    print(f"{'='*60}")
    pdf_path = generate_pdf_report(results)

    # Print summary
    print(f"\n{'='*60}")
    print("✅ DONE")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['scene_id']}: {r['final_coverage_pct']:.1f}% coverage")
    print(f"  Report: {pdf_path}")
    print(f"  Work dir: {WORK_DIR}")


if __name__ == "__main__":
    main()
