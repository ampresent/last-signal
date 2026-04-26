#!/usr/bin/env python3
"""
Green screen cutout with visual model verification.
Uses HSV color space to specifically target green background.
Iterates threshold until mimo-omni confirms clean edges.
"""

import cv2
import numpy as np
from PIL import Image
import os
import subprocess
import sys

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets/sprites"
MIMO_SCRIPT = "/root/.openclaw/skills/mimo-omni/mimo_api.sh"
CHAR = "kai"
TARGET_W = 64
TARGET_H = 128


def green_screen_cutout(img_rgb, green_low, green_high, edge_erode=1):
    """
    HSV-based green screen removal.
    
    img_rgb: numpy array (H, W, 3) uint8
    green_low: (H, S, V) lower bound for green detection
    green_high: (H, S, V) upper bound for green detection
    edge_erode: erosion iterations for edge cleanup
    """
    # Convert to HSV
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    
    # Create green mask (what IS green screen)
    green_mask = cv2.inRange(hsv, np.array(green_low), np.array(green_high))
    
    # Also catch very bright/desaturated greenish tones
    # Low saturation + greenish hue = light green reflections
    h, s, v = cv2.split(hsv)
    greenish_hue = (h > 30) & (h < 90)  # wide green hue range
    low_sat = s < 60
    bright = v > 180
    bright_green = (greenish_hue & low_sat & bright).astype(np.uint8) * 255
    green_mask = cv2.bitwise_or(green_mask, bright_green)
    
    # Morphological cleanup on green mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Invert to get foreground mask
    alpha = 255 - green_mask
    
    # Edge erosion to remove green fringe
    if edge_erode > 0:
        erode_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha = cv2.erode(alpha, erode_k, iterations=edge_erode)
    
    # Final cleanup
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
    
    return alpha


def verify_cutout(webp_path):
    """Visual model verification - specifically check for green fringe."""
    try:
        result = subprocess.run(
            ["bash", MIMO_SCRIPT, "image", webp_path,
             "这是绿幕抠图结果。仔细检查角色边缘是否有任何绿色残留（绿色杂边、绿色光晕、绿色渗透）。只回答：CLEAN（无绿色）或 GREEN（有绿色残留）。"],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip().upper()
        passed = "CLEAN" in output and "GREEN" not in output.replace("CLEAN", "")
        return passed, output
    except Exception as e:
        return False, str(e)


def process_frame(input_path, output_path):
    """
    Process a single frame with green screen cutout.
    Iterates: increase erosion + adjust green range until verification passes.
    """
    img = Image.open(input_path).convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3]
    
    # Green screen HSV ranges to try (from narrow to wide)
    # Standard green screen: H=35-85, S=40-255, V=40-255
    configs = [
        # (green_low, green_high, edge_erode) - progressively more aggressive
        ((35, 40, 40), (85, 255, 255), 1),    # standard
        ((30, 30, 30), (90, 255, 255), 1),    # wider hue range
        ((25, 25, 25), (95, 255, 255), 2),    # even wider + more erosion
        ((20, 20, 20), (100, 255, 255), 2),   # aggressive
        ((15, 15, 15), (105, 255, 255), 3),   # max aggression
    ]
    
    for attempt, (gl, gh, erode) in enumerate(configs):
        alpha = green_screen_cutout(rgb, gl, gh, erode)
        
        result_arr = arr.copy()
        result_arr[:, :, 3] = alpha
        result_arr[alpha == 0, :3] = 0
        
        result = Image.fromarray(result_arr)
        canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        offset_y = (TARGET_H - result.height) // 2
        canvas.paste(result, (0, offset_y))
        
        canvas.save(output_path, "WebP", lossless=True, quality=100)
        
        fg_pct = (alpha > 0).sum() / alpha.size * 100
        print(f"  Attempt {attempt+1}: H={gl[0]}-{gh[0]}, erode={erode}, fg={fg_pct:.1f}%", end="")
        
        passed, reason = verify_cutout(output_path)
        if passed:
            print(f" ✅ CLEAN")
            return True, attempt+1
        else:
            print(f" ❌ {reason[:60]}")
    
    print(f"  ⚠️  Using most aggressive config")
    return False, len(configs)


def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "left"
    input_dir = sys.argv[2] if len(sys.argv) > 2 else f"/root/.openclaw/workspace/{direction}_selected"
    
    files = sorted([f for f in os.listdir(input_dir) if f.endswith('.png')])
    print(f"Green screen cutout — {direction}: {len(files)} frames from {input_dir}\n")
    
    results = []
    for idx, fname in enumerate(files):
        input_path = os.path.join(input_dir, fname)
        output_path = os.path.join(OUTPUT_DIR, f"{CHAR}_{direction}_f{idx}.webp")
        print(f"--- {CHAR}_{direction}_f{idx}.webp ---")
        passed, attempts = process_frame(input_path, output_path)
        results.append((fname, passed, attempts))
    
    print(f"\n{'='*50}")
    passed_count = sum(1 for _, p, _ in results if p)
    print(f"Results: {passed_count}/{len(results)} passed verification")
    for fname, passed, attempts in results:
        status = "✅" if passed else "⚠️"
        print(f"  {status} {fname} ({attempts} attempts)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
