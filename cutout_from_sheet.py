#!/usr/bin/env python3
"""
cutout_from_sheet.py — 从 sprite sheet 提取逐帧 cutout

策略：颜色距离抠图
  1. 拆帧
  2. 从上边缘采样背景色
  3. alpha=255 且颜色远离背景色 → 前景
  4. 形态学清理
  5. 清零背景 RGB → WebP (lossless RGBA)

Usage:
    python3 cutout_from_sheet.py
    python3 cutout_from_sheet.py --char kai
    python3 cutout_from_sheet.py --threshold 25
"""

import argparse
import os

import cv2
import numpy as np
from PIL import Image

SPRITES_DIR = "assets/sprites"
FRAME_W = 64
FRAME_H = 128
DEFAULT_THRESHOLD = 20


def split_sheet(sheet_path):
    sheet = Image.open(sheet_path).convert("RGBA")
    arr = np.array(sheet)
    w = arr.shape[1]

    alpha = arr[:, :, 3]
    col_has_content = np.any(alpha > 10, axis=0)

    if np.all(col_has_content):
        n_frames = w // FRAME_W
        return [Image.fromarray(arr[:, i * FRAME_W : (i + 1) * FRAME_W, :]) for i in range(n_frames)]

    changes = np.diff(col_has_content.astype(int))
    starts = np.where(changes == 1)[0] + 1
    ends = np.where(changes == -1)[0] + 1
    if col_has_content[0]:
        starts = np.insert(starts, 0, 0)
    if col_has_content[-1]:
        ends = np.append(ends, w)

    frames = []
    for s, e in zip(starts, ends):
        block_w = e - s
        if block_w >= FRAME_W:
            crop = arr[:, s : s + FRAME_W, :]
        else:
            pad_total = FRAME_W - block_w
            pad_left = pad_total // 2
            crop = np.zeros((FRAME_H, FRAME_W, 4), dtype=np.uint8)
            crop[:, pad_left : pad_left + block_w, :] = arr[:, s:e, :]
        frames.append(Image.fromarray(crop))

    return frames


def color_cutout(frame_rgba, bg_color, threshold=DEFAULT_THRESHOLD):
    """
    颜色距离抠图：
    - alpha=0 → 背景
    - alpha=255 且颜色接近 bg_color → 背景
    - alpha=255 且颜色远离 bg_color → 前景
    """
    arr = np.array(frame_rgba)
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]

    # 颜色距离
    dist = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))

    # 前景 = alpha=255 且颜色远离背景色
    fg_mask = ((alpha == 255) & (dist > threshold)).astype(np.uint8) * 255

    # 形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    return fg_mask


def process_character(char_id, directions=None, threshold=DEFAULT_THRESHOLD):
    dirs = directions or ["down", "left", "right", "up"]

    for d in dirs:
        sheet_path = os.path.join(SPRITES_DIR, f"sheet_{char_id}_{d}.webp")
        if not os.path.exists(sheet_path):
            print(f"  ⚠️  跳过 {d}")
            continue

        print(f"\n📂 {sheet_path}")
        frames = split_sheet(sheet_path)
        print(f"   {len(frames)} 帧")

        # 从 sheet 上边缘采样背景色
        sheet_arr = np.array(Image.open(sheet_path).convert("RGBA"))
        bg_color = np.median(
            sheet_arr[0:5, :, :3].reshape(-1, 3).astype(np.float32), axis=0
        )
        print(f"   背景色: {bg_color.astype(int)}")

        for i, frame in enumerate(frames):
            out_path = os.path.join(SPRITES_DIR, f"{char_id}_{d}_f{i}.webp")
            arr = np.array(frame)

            mask = color_cutout(frame, bg_color, threshold)

            # 合成 RGBA
            rgba = arr.copy()
            rgba[:, :, 3] = mask
            bg = mask == 0
            rgba[bg, 0] = 0
            rgba[bg, 1] = 0
            rgba[bg, 2] = 0

            Image.fromarray(rgba).save(out_path, "WebP", lossless=True, quality=100)
            fg_pct = 100 * np.sum(mask > 128) / mask.size
            print(f"   f{i}: fg={fg_pct:.0f}% ✓")

    print("\n✅ 完成")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--char", default="kai")
    parser.add_argument("--dir", nargs="*")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    print(f"🎭 颜色距离抠图 — {args.char} (threshold={args.threshold})")
    process_character(args.char, args.dir, args.threshold)


if __name__ == "__main__":
    main()
