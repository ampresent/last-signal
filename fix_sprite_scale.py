#!/usr/bin/env python3
"""
Fix sprite content size inconsistency across directions.
Scales character content in undersized directions to match the tallest.
"""
from PIL import Image
import glob
import os

SPRITE_DIR = os.path.join(os.path.dirname(__file__), "assets", "sprites")
CHAR = "kai"
TARGET_W, TARGET_H = 64, 128

def get_content_stats(direction):
    """Get average content height and top-y for a direction."""
    files = sorted(glob.glob(os.path.join(SPRITE_DIR, f"{CHAR}_{direction}_f*.webp")))
    heights, tops = [], []
    for f in files:
        img = Image.open(f).convert("RGBA")
        bbox = img.getbbox()
        if bbox:
            heights.append(bbox[3] - bbox[1])
            tops.append(bbox[1])
    if not heights:
        return 0, 0
    return sum(heights) / len(heights), sum(tops) / len(tops)

def rescale_direction(direction, target_h):
    """Rescale all frames of a direction so content matches target_h."""
    files = sorted(glob.glob(os.path.join(SPRITE_DIR, f"{CHAR}_{direction}_f*.webp")))
    print(f"\n{'─'*50}")
    print(f"Fixing {direction} → target content height: {target_h:.0f}px")
    print(f"{'─'*50}")

    for f in files:
        img = Image.open(f).convert("RGBA")
        bbox = img.getbbox()
        if not bbox:
            print(f"  {os.path.basename(f)}: empty, skip")
            continue

        x1, y1, x2, y2 = bbox
        content_w = x2 - x1
        content_h = y2 - y1
        scale = target_h / content_h
        new_w = max(1, round(content_w * scale))
        new_h = max(1, round(content_h * scale))

        # Extract content, scale it
        content = img.crop(bbox)
        content_resized = content.resize((new_w, new_h), Image.LANCZOS)

        # Center on canvas
        canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
        paste_x = (TARGET_W - new_w) // 2
        paste_y = (TARGET_H - new_h) // 2
        canvas.paste(content_resized, (paste_x, paste_y))

        canvas.save(f, "WebP", lossless=True, quality=100)
        print(f"  {os.path.basename(f)}: {content_w}x{content_h} → {new_w}x{new_h} (scale={scale:.3f})")

def main():
    # Gather stats for all directions
    stats = {}
    for d in ['up', 'down', 'left', 'right']:
        avg_h, avg_top = get_content_stats(d)
        stats[d] = {'avg_h': avg_h, 'avg_top': avg_top}
        print(f"{d}: avg content h={avg_h:.1f}px, avg top y={avg_top:.1f}px")

    # Target = max average content height across all directions
    target_h = max(s['avg_h'] for s in stats.values())
    print(f"\nTarget content height: {target_h:.1f}px")

    # Fix directions that are significantly smaller (more than 5% off)
    for d, s in stats.items():
        if s['avg_h'] < target_h * 0.95:
            rescale_direction(d, target_h)
        else:
            print(f"\n{d}: OK ({s['avg_h']:.1f}px >= {target_h*0.95:.1f}px), skip")

if __name__ == "__main__":
    main()
