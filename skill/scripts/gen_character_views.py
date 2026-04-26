#!/usr/bin/env python3
"""
gen_character_views.py — Character view generator: front → img2img (left/right/back)

Pipeline:
  1. Generate front-facing (down) full-body character via Pollinations text2img
  2. Cutout → RGBA transparent background
  3. Use front cutout as init image for img2img → left, right, back views
  4. Cutout each direction
  5. Output: cutout_{char}_{dir}.webp for all 4 directions

Then run: python3 cutout_from_sheet.py

Usage:
    python3 gen_character_views.py              # all characters
    python3 gen_character_views.py --char joker # single character
    python3 gen_character_views.py --front-only # only generate/cutout front
"""

import argparse
import io
import os
import sys
import time
import urllib.request
import urllib.parse

OUTPUT_DIR = "assets/sprites"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://image.pollinations.ai/prompt/"
IMG_SIZE = 256  # generation resolution
SEED_BASE = 2087


# ── Character Definitions ──────────────────────────────────────────

SPRITE_STYLE = (
    "pixel art character sprite, 16-bit retro game, cyberpunk noir style, "
    "single character standing pose, full body from head to feet, "
    "centered in frame, clean pixel art, limited color palette, "
    "transparent background, isolated character, no text, no labels, "
    "game character asset, high quality, entire body visible including head hands and feet"
)

CHARACTERS = {
    "joker": {
        "name": "谐子",
        "desc": (
            "a chaotic male hacker in a cyberpunk world, "
            "wearing a colorful patched coat with LED strips, "
            "wild spiky hair with neon streaks, manic grin, "
            "fingerless gloves, tech-gadget belt, boots"
        ),
        "palette": "neon magenta, electric blue, yellow accents, black",
    },
    "kai": {
        "name": "凯",
        "desc": (
            "a tired middle-aged male detective in a cyberpunk world, "
            "wearing worn brown leather jacket, dark pants, boots, "
            "short messy black hair, stubble, determined tired eyes"
        ),
        "palette": "dark browns, grays, muted blue accents",
    },
    "oracle": {
        "name": "Oracle",
        "desc": (
            "a mysterious female hacker in a cyberpunk world, "
            "wearing dark hooded jacket with neon trim, cargo pants, boots, "
            "short asymmetric purple hair, glowing neon-green eyes, "
            "goggles on forehead"
        ),
        "palette": "dark purple, black, neon green accents",
    },
}

DIRECTIONS = {
    "down": {
        "facing": "facing viewer, front view, 3/4 view from slightly above",
        "seed_offset": 0,
    },
    "left": {
        "facing": "facing left, left side view, left profile, character turned 90 degrees to the left",
        "seed_offset": 100,
    },
    "right": {
        "facing": "facing right, right side view, right profile, character turned 90 degrees to the right",
        "seed_offset": 200,
    },
    "up": {
        "facing": "facing away from viewer, back view, character seen from behind",
        "seed_offset": 300,
    },
}


# ── Download / Upload ──────────────────────────────────────────────

def download(url, filepath, timeout=180):
    """Download image from URL, skip if exists."""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 5000:
        print(f"   ⏭️  已有: {os.path.basename(filepath)}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"   ✅ {os.path.basename(filepath)} ({len(data)//1024}KB)")
            return True
    except Exception as e:
        print(f"   ❌ {os.path.basename(filepath)}: {e}")
        return False


def img2img(init_image_path, prompt, output_path, seed=None, width=None, height=None, timeout=180):
    """Use Pollinations.AI img2img: send init image + prompt, get transformed image.

    POST multipart/form-data with 'image' field.
    """
    if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
        print(f"   ⏭️  已有: {os.path.basename(output_path)}")
        return True

    w = width or IMG_SIZE
    h = height or IMG_SIZE
    s = seed or SEED_BASE

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"{BASE_URL}{encoded_prompt}?width={w}&height={h}&seed={s}&model=flux&nologo=true"

    # Build multipart form data
    boundary = "----PythonBoundary" + str(int(time.time()))
    body = io.BytesIO()

    # Add image file
    with open(init_image_path, "rb") as f:
        image_data = f.read()

    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="image"; filename="init.png"\r\n')
    body.write(b"Content-Type: image/png\r\n\r\n")
    body.write(image_data)
    body.write(b"\r\n")

    body.write(f"--{boundary}--\r\n".encode())

    body_bytes = body.getvalue()

    try:
        req = urllib.request.Request(
            url,
            data=body_bytes,
            method="POST",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            with open(output_path, "wb") as f:
                f.write(data)
            print(f"   ✅ img2img → {os.path.basename(output_path)} ({len(data)//1024}KB)")
            return True
    except Exception as e:
        print(f"   ❌ img2img failed: {e}")
        return False


# ── Cutout (rembg → fallback) ──────────────────────────────────────

def cutout(input_path, output_path):
    """Remove background → RGBA transparent WebP."""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
        print(f"   ⏭️  抠图已有: {os.path.basename(output_path)}")
        return True

    # Try rembg first
    try:
        from rembg import remove
        with open(input_path, "rb") as f:
            input_data = f.read()
        output_data = remove(input_data)
        # rembg outputs PNG, convert to WebP
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(output_data)).convert("RGBA")
        img.save(output_path, "WebP", lossless=True, quality=100)
        print(f"   🎭 抠图完成 (rembg): {os.path.basename(output_path)} ({os.path.getsize(output_path)//1024}KB)")
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️  rembg 失败: {e}, 尝试 fallback...")

    # Fallback: simple threshold cutout for pixel art
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(input_path).convert("RGBA")
        arr = np.array(img)

        # Detect background: corners are usually background
        corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
        bg_color = np.median(corners, axis=0).astype(np.uint8)[:3]

        # Distance from background color
        rgb = arr[:, :, :3].astype(np.float32)
        bg = bg_color.astype(np.float32)
        dist = np.sqrt(np.sum((rgb - bg) ** 2, axis=2))

        # Threshold: pixels close to bg color are background
        threshold = 40
        alpha = np.where(dist > threshold, 255, 0).astype(np.uint8)

        # Clean up: erode + dilate to remove noise
        import cv2
        kernel = np.ones((3, 3), np.uint8)
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel)
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel)

        arr[:, :, 3] = alpha
        result = Image.fromarray(arr)
        result.save(output_path, "WebP", lossless=True, quality=100)
        print(f"   🎭 抠图完成 (fallback): {os.path.basename(output_path)}")
        return True
    except Exception as e:
        print(f"   ❌ 抠图失败: {e}")
        return False


# ── Pipeline ───────────────────────────────────────────────────────

def process_character(char_id, front_only=False, force=False):
    """Generate all 4 direction views for a character.

    Flow:
      1. text2img → raw_{char}_down.png (front)
      2. cutout → cutout_{char}_down.webp
      3. img2img(front) → raw_{char}_{left,right,up}.png
      4. cutout → cutout_{char}_{left,right,up}.webp
    """
    char = CHARACTERS[char_id]
    print(f"\n{'='*55}")
    print(f"👤 {char['name']} ({char_id})")
    print(f"{'='*55}")

    # ── Step 1: Generate front (down) ──
    front_raw = os.path.join(OUTPUT_DIR, f"raw_{char_id}_down.png")
    front_cutout = os.path.join(OUTPUT_DIR, f"cutout_{char_id}_down.webp")

    front_prompt = (
        f"{SPRITE_STYLE}, {char['desc']}, "
        f"{DIRECTIONS['down']['facing']}, "
        f"colors: {char['palette']}"
    )
    front_seed = SEED_BASE + DIRECTIONS["down"]["seed_offset"]

    print(f"\n   ── 正面 (down) ──")
    if force or not os.path.exists(front_raw) or os.path.getsize(front_raw) < 5000:
        ok = download(
            f"{BASE_URL}{urllib.parse.quote(front_prompt)}?width={IMG_SIZE}&height={IMG_SIZE}&seed={front_seed}&model=flux&nologo=true",
            front_raw,
        )
        if not ok:
            print("   ❌ 正面生成失败，终止")
            return False
    else:
        print(f"   ⏭️  正面已有: {os.path.basename(front_raw)}")

    # Cutout front
    if force or not os.path.exists(front_cutout) or os.path.getsize(front_cutout) < 5000:
        cutout(front_raw, front_cutout)
    else:
        print(f"   ⏭️  正面抠图已有")

    if front_only:
        print(f"\n   ✅ front-only 模式完成")
        return True

    # ── Step 2: img2img → left, right, back ──
    other_dirs = ["left", "right", "up"]

    for direction in other_dirs:
        dinfo = DIRECTIONS[direction]
        print(f"\n   ── {direction} (img2img from front) ──")

        other_raw = os.path.join(OUTPUT_DIR, f"raw_{char_id}_{direction}.png")
        other_cutout = os.path.join(OUTPUT_DIR, f"cutout_{char_id}_{direction}.webp")

        if not force and os.path.exists(other_cutout) and os.path.getsize(other_cutout) > 5000:
            print(f"   ⏭️  {direction} 已有")
            continue

        # Build img2img prompt: same character, different angle
        direction_prompt = (
            f"{SPRITE_STYLE}, {char['desc']}, "
            f"{dinfo['facing']}, "
            f"colors: {char['palette']}, "
            f"same character design as reference, same outfit, same colors, "
            f"pixel art game sprite"
        )
        direction_seed = SEED_BASE + dinfo["seed_offset"]

        # img2img from front cutout
        ok = img2img(
            front_cutout,
            direction_prompt,
            other_raw,
            seed=direction_seed,
        )

        if not ok:
            # Fallback: text2img without init image
            print(f"   ⚠️  img2img 失败，降级为 text2img...")
            fallback_url = (
                f"{BASE_URL}{urllib.parse.quote(direction_prompt)}"
                f"?width={IMG_SIZE}&height={IMG_SIZE}&seed={direction_seed}&model=flux&nologo=true"
            )
            ok = download(fallback_url, other_raw)

        if ok:
            cutout(other_raw, other_cutout)
        else:
            print(f"   ❌ {direction} 生成失败")

        time.sleep(2)  # rate limit

    print(f"\n   ✅ {char_id} 全部方向完成")
    return True


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="LAST SIGNAL 角色视角生成器 (front → img2img → 4 directions)"
    )
    parser.add_argument("--char", type=str, help="单个角色 (joker/kai/oracle)")
    parser.add_argument("--front-only", action="store_true", help="只生成正面")
    parser.add_argument("--force", action="store_true", help="强制重新生成")
    args = parser.parse_args()

    print("=" * 55)
    print("🎮 LAST SIGNAL - 角色视角生成器")
    print(f"   输出: {OUTPUT_DIR}")
    print(f"   流程: 正面(text2img) → 抠图 → 其他角度(img2img) → 抠图")
    print("=" * 55)

    chars = [args.char] if args.char else list(CHARACTERS.keys())

    for char_id in chars:
        if char_id not in CHARACTERS:
            print(f"❌ 未知角色: {char_id}")
            continue
        process_character(char_id, front_only=args.front_only, force=args.force)

    print(f"\n{'='*55}")
    print(f"✅ 全部完成！")
    print(f"   下一步: python3 cutout_from_sheet.py")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
