#!/usr/bin/env python3
"""
Improved cutout with visual model verification.
Iterates threshold until the visual model confirms clean edges.
"""

import cv2
import numpy as np
from PIL import Image
import os
import subprocess
import json
import sys

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets/sprites"
MIMO_SCRIPT = "/root/.openclaw/skills/mimo-omni/mimo_api.sh"
CHAR = "kai"
TARGET_W = 64
TARGET_H = 128


def sample_bg_color(rgb):
    """Sample background from all 4 edges (top, bottom, left, right strips)."""
    h, w = rgb.shape[:2]
    strips = [
        rgb[:6, :, :],        # top
        rgb[-6:, :, :],       # bottom
        rgb[:, :6, :],        # left
        rgb[:, -6:, :],       # right
    ]
    all_edge = np.concatenate([s.reshape(-1, 3) for s in strips])
    # Use the mode-like approach: cluster and pick the largest cluster center
    # Simple: median of all edge pixels
    bg_color = np.median(all_edge, axis=0)
    return bg_color


def adaptive_cutout(img_rgb, threshold):
    """Color-distance cutout with adaptive background sampling."""
    rgb = img_rgb[:, :, :3].astype(np.float32)
    bg_color = sample_bg_color(rgb)

    # Color distance
    dist = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))

    # Foreground mask
    alpha = ((dist > threshold) * 255).astype(np.uint8)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel, iterations=1)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Edge erosion to remove color fringing
    erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    alpha_eroded = cv2.erode(alpha, erode_kernel, iterations=1)

    return alpha_eroded, bg_color


def verify_cutout(webp_path):
    """Use mimo-omni to verify cutout quality. Returns (pass, reason)."""
    try:
        result = subprocess.run(
            ["bash", MIMO_SCRIPT, "image", webp_path,
             "检查这个角色sprite抠图质量。问题：1.边缘是否有残留背景色杂边（绿色/白色/灰色）？2.角色内部是否有洞？3.背景是否完全透明？请简短回答每个问题的yes/no。"],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        # Parse: look for keywords
        has_fringe = "有" in output and ("杂边" in output or "残留" in output or "绿色" in output or "白色" in output)
        has_holes = "有" in output and "洞" in output
        bg_transparent = "完全透明" in output and "是" in output

        # Pass if no fringe and no holes
        passed = not has_fringe and not has_holes
        return passed, output
    except Exception as e:
        return False, str(e)


def process_frame(input_path, output_path, initial_threshold=30, max_attempts=5):
    """Process a single frame with iterative threshold tuning."""
    img = Image.open(input_path).convert("RGBA")
    arr = np.array(img)

    best_threshold = initial_threshold
    best_alpha = None

    for attempt in range(max_attempts):
        threshold = initial_threshold + attempt * 10  # 30, 40, 50, 60, 70
        alpha, bg_color = adaptive_cutout(arr, threshold)

        # Apply alpha
        result_arr = arr.copy()
        result_arr[:, :, 3] = alpha
        result_arr[alpha == 0, :3] = 0

        # Pad to target size
        result = Image.fromarray(result_arr)
        canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        offset_y = (TARGET_H - result.height) // 2
        canvas.paste(result, (0, offset_y))

        # Save temp for verification
        temp_path = output_path.replace(".webp", "_temp.webp")
        canvas.save(temp_path, "WebP", lossless=True, quality=100)

        fg_pct = (alpha > 0).sum() / alpha.size * 100
        print(f"  Attempt {attempt+1}: threshold={threshold}, fg={fg_pct:.1f}%", end="")

        # Verify
        passed, reason = verify_cutout(temp_path)
        if passed:
            print(f" ✅ PASS")
            # Save final
            canvas.save(output_path, "WebP", lossless=True, quality=100)
            os.remove(temp_path)
            return True, threshold
        else:
            print(f" ❌ FAIL: {reason[:80]}")
            best_threshold = threshold
            best_alpha = alpha

    # If all attempts fail, save the best one (highest threshold = most aggressive removal)
    print(f"  ⚠️  Using best attempt (threshold={best_threshold})")
    result_arr = arr.copy()
    result_arr[:, :, 3] = best_alpha
    result_arr[best_alpha == 0, :3] = 0
    result = Image.fromarray(result_arr)
    canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    offset_y = (TARGET_H - result.height) // 2
    canvas.paste(result, (0, offset_y))
    canvas.save(output_path, "WebP", lossless=True, quality=100)
    temp_path = output_path.replace(".webp", "_temp.webp")
    if os.path.exists(temp_path):
        os.remove(temp_path)
    return False, best_threshold


def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "left"
    input_dir = sys.argv[2] if len(sys.argv) > 2 else f"/root/.openclaw/workspace/{direction}_selected_v2"

    files = sorted([f for f in os.listdir(input_dir) if f.endswith('.png')])
    print(f"Processing {direction}: {len(files)} frames from {input_dir}")

    results = []
    for idx, fname in enumerate(files):
        input_path = os.path.join(input_dir, fname)
        output_path = os.path.join(OUTPUT_DIR, f"{CHAR}_{direction}_f{idx}.webp")
        print(f"\n--- {CHAR}_{direction}_f{idx}.webp ---")
        passed, threshold = process_frame(input_path, output_path)
        results.append((fname, passed, threshold))

    print(f"\n{'='*50}")
    print(f"Results for {direction}:")
    for fname, passed, threshold in results:
        status = "✅" if passed else "⚠️"
        print(f"  {status} {fname} → threshold={threshold}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
