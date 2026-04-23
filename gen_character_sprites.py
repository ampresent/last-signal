"""
LAST SIGNAL - 角色行走图生成器 (Sprite Sheet 方式)
每个方向生成一张 512×128 的横条图 (4帧)，切分为 4 张 128×128
保证同一方向的 4 帧人物长相一致

用法:
    python3 gen_character_sprites.py              # 全部角色
    python3 gen_character_sprites.py --char kai   # 单个角色
"""
import urllib.request
import urllib.parse
import os
import sys
import time
import argparse

try:
    from PIL import Image
except ImportError:
    print("需要 Pillow: pip install Pillow")
    sys.exit(1)

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets/sprites"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"

# ── 基础风格 ──
SPRITE_STYLE = (
    "pixel art sprite sheet, 16-bit retro game, cyberpunk noir style, "
    "4 frames of walk cycle animation arranged horizontally left to right, "
    "same character in all 4 frames, consistent appearance and colors, "
    "transparent background, clean pixel art, limited color palette, "
    "no text, no labels, no border, game character asset, "
    "frame 1: standing, frame 2: right foot forward, frame 3: standing, frame 4: left foot forward"
)

# ── 角色定义 ──
CHARACTERS = {
    "kai": {
        "name": "凯",
        "base_prompt": (
            "a tired middle-aged male detective in a cyberpunk world, "
            "wearing worn brown leather jacket, dark pants, boots, "
            "short messy black hair, stubble, determined tired eyes"
        ),
        "palette": "dark browns, grays, muted blue accents",
    },
    "oracle": {
        "name": "Oracle",
        "base_prompt": (
            "a mysterious female hacker in a cyberpunk world, "
            "wearing dark hooded jacket with neon trim, cargo pants, "
            "short asymmetric purple hair, glowing neon-green eyes, "
            "goggles on forehead"
        ),
        "palette": "dark purple, black, neon green accents",
    },
    "joker": {
        "name": "谐子",
        "base_prompt": (
            "a chaotic male hacker in a cyberpunk world, "
            "wearing a colorful patched coat with LED strips, "
            "wild spiky hair with neon streaks, manic grin, "
            "fingerless gloves, tech-gadget belt"
        ),
        "palette": "neon magenta, electric blue, yellow accents, black",
    },
}

# ── 方向定义 ──
DIRECTIONS = {
    "down":  {"facing": "facing viewer, front view, 3/4 view from slightly above",  "seed_offset": 0},
    "left":  {"facing": "facing left, side view, left profile walking left",         "seed_offset": 100},
    "right": {"facing": "facing right, side view, right profile walking right",      "seed_offset": 200},
    "up":    {"facing": "facing away from viewer, back view, walking away",          "seed_offset": 300},
}

FRAME_W = 128
FRAME_H = 128
FRAMES = 4
SHEET_W = FRAME_W * FRAMES  # 512
SEED_BASE = 2087


def download(url, filepath):
    """下载图片，跳过已存在的文件"""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 5000:
        print(f"   ⏭️  已有: {os.path.basename(filepath)}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"   ✅ {os.path.basename(filepath)} ({len(data)//1024}KB)")
            return True
    except Exception as e:
        print(f"   ❌ {os.path.basename(filepath)}: {e}")
        return False


def gen_sheet(char_id, direction):
    """生成一个方向的行走序列横条图 (512×128)"""
    char = CHARACTERS[char_id]
    dinfo = DIRECTIONS[direction]

    prompt = (
        f"{SPRITE_STYLE}, "
        f"{char['base_prompt']}, "
        f"{dinfo['facing']}, "
        f"colors: {char['palette']}, "
        f"4 panel walk cycle sprite sheet horizontal strip"
    )

    seed = SEED_BASE + dinfo["seed_offset"]
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={SHEET_W}&height={FRAME_H}&seed={seed}&model=flux&nologo=true"

    sheet_path = os.path.join(OUTPUT_DIR, f"sheet_{char_id}_{direction}.png")
    return download(url, sheet_path), sheet_path


def slice_sheet(sheet_path, char_id, direction):
    """将横条图切分为 4 张单独帧"""
    try:
        img = Image.open(sheet_path)
    except Exception as e:
        print(f"   ❌ 无法打开 {sheet_path}: {e}")
        return False

    # 如果尺寸不对，resize 到目标尺寸
    if img.size != (SHEET_W, FRAME_H):
        print(f"   ⚠️  尺寸 {img.size} ≠ {SHEET_W}×{FRAME_H}，缩放中...")
        img = img.resize((SHEET_W, FRAME_H), Image.NEAREST)

    ok = True
    for fi in range(FRAMES):
        x = fi * FRAME_W
        frame = img.crop((x, 0, x + FRAME_W, FRAME_H))
        out_path = os.path.join(OUTPUT_DIR, f"{char_id}_{direction}_f{fi}.png")
        frame.save(out_path)
        size = os.path.getsize(out_path)
        if size < 100:
            print(f"   ⚠️  {char_id}_{direction}_f{fi}.png 太小 ({size}B)")
            ok = False
        else:
            print(f"   ✂️  {char_id}_{direction}_f{fi}.png ({size//1024}KB)")

    return ok


def gen_character(char_id, directions=None):
    """生成一个角色的所有行走帧"""
    char = CHARACTERS[char_id]
    dirs = directions or list(DIRECTIONS.keys())

    print(f"\n👤 {char['name']} ({char_id}):")
    ok, fail = 0, 0

    for d in dirs:
        print(f"   方向: {d}")

        # 1. 生成横条图
        sheet_ok, sheet_path = gen_sheet(char_id, d)
        if not sheet_ok:
            fail += FRAMES
            time.sleep(2)
            continue

        # 2. 切分为 4 帧
        if slice_sheet(sheet_path, char_id, d):
            ok += FRAMES
        else:
            fail += FRAMES

        time.sleep(2)  # 避免速率限制

    return ok, fail


def main():
    parser = argparse.ArgumentParser(description="LAST SIGNAL 角色行走图生成器 (Sheet)")
    parser.add_argument("--char", type=str, help="生成单个角色 (kai/oracle/joker)")
    parser.add_argument("--dir", type=str, help="生成单方向 (down/left/right/up)")
    parser.add_argument("--force", action="store_true", help="强制重新生成已有文件")
    args = parser.parse_args()

    if args.force:
        # 删除已有文件强制重新生成
        import glob
        for f in glob.glob(os.path.join(OUTPUT_DIR, "sheet_*.png")):
            os.remove(f)

    print("=" * 55)
    print("🎮 LAST SIGNAL - 角色行走图生成器 (Sprite Sheet)")
    print(f"   输出: {OUTPUT_DIR}")
    print(f"   策略: 每方向生成 {SHEET_W}×{FRAME_H} 横条 → 切分 {FRAMES} 帧")
    print("=" * 55)

    chars = [args.char] if args.char else list(CHARACTERS.keys())
    dirs = [args.dir] if args.dir else None

    total_ok, total_fail = 0, 0

    for char_id in chars:
        if char_id not in CHARACTERS:
            print(f"❌ 未知角色: {char_id} (可选: {', '.join(CHARACTERS.keys())})")
            continue
        ok, fail = gen_character(char_id, dirs)
        total_ok += ok
        total_fail += fail

    print(f"\n{'='*55}")
    print(f"✅ 成功: {total_ok} 帧  ❌ 失败: {total_fail} 帧")
    print(f"📁 {OUTPUT_DIR}")

    # 列出生成的文件
    sprites = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.png') and not f.startswith('sheet_')])
    print(f"\n📋 共 {len(sprites)} 帧:")
    for s in sprites:
        print(f"   {s}")


if __name__ == "__main__":
    main()
