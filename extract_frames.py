#!/usr/bin/env python3
"""从 sprite sheet 提取逐帧 WebP（纯 PIL，无需 cv2）"""
import os
from PIL import Image

SPRITES_DIR = "assets/sprites"
FRAME_W, FRAME_H = 64, 128

def extract_frames(sheet_path, char_id, direction):
    sheet = Image.open(sheet_path).convert("RGBA")
    w, h = sheet.size
    n_frames = w // FRAME_W
    print(f"  {os.path.basename(sheet_path)}: {w}x{h}, {n_frames} frames")
    for i in range(n_frames):
        frame = sheet.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H))
        out_path = os.path.join(SPRITES_DIR, f"{char_id}_{direction}_f{i}.webp")
        frame.save(out_path, "WebP", lossless=True, quality=100)
    print(f"    → {n_frames} frames saved")

def main():
    for fname in sorted(os.listdir(SPRITES_DIR)):
        if not fname.startswith("sheet_") or not fname.endswith(".webp"):
            continue
        # sheet_{char}_{direction}.webp
        parts = fname.replace("sheet_", "").replace(".webp", "").split("_", 1)
        if len(parts) != 2:
            continue
        char_id, direction = parts
        sheet_path = os.path.join(SPRITES_DIR, fname)
        extract_frames(sheet_path, char_id, direction)
    print("\n✅ Done")

if __name__ == "__main__":
    main()
