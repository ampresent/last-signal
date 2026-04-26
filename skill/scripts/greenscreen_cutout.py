#!/usr/bin/env python3
"""
Conservative green screen cutout - ONLY removes pure green pixels.
Does NOT erode edges or detect "bright green" supplements.
Preserves character detail by being very targeted.
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


def conservative_green_cutout(img_rgb, h_low=35, h_high=85, s_min=50, v_min=50):
    """
    Conservative green screen removal - ONLY targets pure green pixels.
    No edge erosion, no bright-green supplement, no aggressive morphing.
    """
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    
    # Only detect pure green pixels (narrow, targeted)
    green_mask = cv2.inRange(hsv, 
                             np.array([h_low, s_min, v_min]), 
                             np.array([h_high, 255, 255]))
    
    # Minimal morphological cleanup - just close small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    
    # Invert to get foreground
    alpha = 255 - green_mask
    
    # NO erosion - don't touch character edges
    # NO opening - don't remove character detail
    
    return alpha


def verify_cutout(webp_path):
    """Check for green fringe AND character completeness."""
    try:
        result = subprocess.run(
            ["bash", MIMO_SCRIPT, "image", webp_path,
             "检查这个角色sprite：1.角色边缘有绿色残留吗？2.角色身体/四肢是否完整（有没有被切掉的部分）？3.背景透明吗？简短回答每个问题。"],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        has_green = "有" in output and ("绿色" in output or "残留" in output or "杂边" in output)
        has_incomplete = "不完整" in output or "切掉" in output or "缺失" in output or "被切" in output
        passed = not has_green and not has_incomplete
        return passed, output
    except Exception as e:
        return False, str(e)


def process_frame(input_path, output_path):
    """Process single frame with conservative green cutout."""
    img = Image.open(input_path).convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3]
    
    # Iteration: widen green range slightly if needed
    configs = [
        (35, 85, 50, 50),   # standard
        (33, 87, 45, 45),   # slightly wider
        (30, 90, 40, 40),   # wider
        (28, 92, 35, 35),   # wider still
        (25, 95, 30, 30),   # max
    ]
    
    for attempt, (hl, hh, sv, vv) in enumerate(configs):
        alpha = conservative_green_cutout(rgb, hl, hh, sv, vv)
        
        result_arr = arr.copy()
        result_arr[:, :, 3] = alpha
        result_arr[alpha == 0, :3] = 0
        
        result = Image.fromarray(result_arr)
        canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        offset_y = (TARGET_H - result.height) // 2
        canvas.paste(result, (0, offset_y))
        
        canvas.save(output_path, "WebP", lossless=True, quality=100)
        
        fg_pct = (alpha > 0).sum() / alpha.size * 100
        green_pct = (alpha == 0).sum() / alpha.size * 100 - (100 - fg_pct)
        print(f"  Attempt {attempt+1}: H={hl}-{hh}, fg={fg_pct:.1f}%", end="")
        
        passed, reason = verify_cutout(output_path)
        if passed:
            print(f" ✅ CLEAN + COMPLETE")
            return True, attempt+1
        else:
            print(f" ❌ {reason[:60]}")
    
    print(f"  ⚠️  Using best attempt")
    return False, len(configs)


def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "left"
    input_dir = sys.argv[2] if len(sys.argv) > 2 else f"/root/.openclaw/workspace/{direction}_selected"
    
    files = sorted([f for f in os.listdir(input_dir) if f.endswith('.png')])
    print(f"Conservative green screen cutout — {direction}: {len(files)} frames\n")
    
    results = []
    for idx, fname in enumerate(files):
        input_path = os.path.join(input_dir, fname)
        output_path = os.path.join(OUTPUT_DIR, f"{CHAR}_{direction}_f{idx}.webp")
        print(f"--- {CHAR}_{direction}_f{idx}.webp ---")
        passed, attempts = process_frame(input_path, output_path)
        results.append((fname, passed, attempts))
    
    print(f"\n{'='*50}")
    passed_count = sum(1 for _, p, _ in results if p)
    print(f"Results: {passed_count}/{len(results)} passed")
    for fname, passed, attempts in results:
        status = "✅" if passed else "⚠️"
        print(f"  {status} {fname} ({attempts} attempts)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
