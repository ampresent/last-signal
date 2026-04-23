"""
LAST SIGNAL - 角色行走图生成器
使用 Pollinations.AI 生成角色行走动画帧

每个角色生成 4方向 × 4帧 = 16 张行走图
方向: down(正面), left(左), right(右), up(背面)
帧: f0(站立), f1(迈步1), f2(站立), f3(迈步2) — 循环

用法:
    python3 gen_character_sprites.py              # 全部角色
    python3 gen_character_sprites.py --char kai   # 单个角色
    python3 gen_character_sprites.py --dir down   # 单方向
"""
import urllib.request
import urllib.parse
import os
import sys
import time
import argparse

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets/sprites"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"

# ── 基础风格 ──
SPRITE_STYLE = (
    "pixel art, 16-bit retro game sprite, cyberpunk noir, "
    "full body character, standing pose, walk cycle frame, "
    "transparent background, game asset, clean pixel art, "
    "limited color palette, no text, no border, single character"
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
    "down":  {"facing": "facing viewer, front view",          "seed_offset": 0},
    "left":  {"facing": "facing left, side view, left profile", "seed_offset": 100},
    "right": {"facing": "facing right, side view, right profile", "seed_offset": 200},
    "up":    {"facing": "facing away, back view",              "seed_offset": 300},
}

# ── 帧定义 (行走循环) ──
# f0=左脚站立, f1=右脚迈出, f2=右脚站立, f3=左脚迈出
FRAMES = {
    0: "standing pose, weight on left foot, arms relaxed",
    1: "walking pose, right foot forward, left foot back, arms swinging",
    2: "standing pose, weight on right foot, arms relaxed",
    3: "walking pose, left foot forward, right foot back, arms swinging",
}

SPRITE_SIZE = 128  # 128×128 像素
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


def gen_sprite(char_id, direction, frame_idx):
    """生成单个行走帧"""
    char = CHARACTERS[char_id]
    dinfo = DIRECTIONS[direction]
    frame_desc = FRAMES[frame_idx]

    prompt = (
        f"{SPRITE_STYLE}, {char['base_prompt']}, "
        f"{dinfo['facing']}, {frame_desc}, "
        f"colors: {char['palette']}, "
        f"viewed from {'top-down slight angle' if direction != 'up' else 'behind'} "
        f"adventure game character sprite"
    )

    seed = SEED_BASE + dinfo["seed_offset"] + frame_idx
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={SPRITE_SIZE}&height={SPRITE_SIZE}&seed={seed}&model=flux&nologo=true"

    filename = f"{char_id}_{direction}_f{frame_idx}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    return download(url, filepath)


def gen_character(char_id, directions=None):
    """生成一个角色的所有行走帧"""
    char = CHARACTERS[char_id]
    dirs = directions or list(DIRECTIONS.keys())

    print(f"\n👤 {char['name']} ({char_id}):")
    ok, fail = 0, 0

    for d in dirs:
        print(f"   方向: {d}")
        for fi in range(4):
            if gen_sprite(char_id, d, fi):
                ok += 1
            else:
                fail += 1
            time.sleep(1.5)  # 避免速率限制

    return ok, fail


def gen_walk_sheet(char_id, direction):
    """为指定角色+方向生成行走序列参考图（拼合4帧到一行）"""
    try:
        from PIL import Image
    except ImportError:
        print("   ⚠️  需要 Pillow: pip install Pillow")
        return

    frames = []
    for fi in range(4):
        path = os.path.join(OUTPUT_DIR, f"{char_id}_{direction}_f{fi}.png")
        if os.path.exists(path):
            frames.append(Image.open(path))

    if len(frames) != 4:
        print(f"   ⚠️  {char_id}_{direction} 帧不完整 ({len(frames)}/4)")
        return

    # 拼合为一张参考图 (4帧横排)
    sheet = Image.new("RGBA", (SPRITE_SIZE * 4, SPRITE_SIZE), (0, 0, 0, 0))
    for i, img in enumerate(frames):
        sheet.paste(img, (i * SPRITE_SIZE, 0))

    out_path = os.path.join(OUTPUT_DIR, f"sheet_{char_id}_{direction}.png")
    sheet.save(out_path)
    print(f"   📋 参考图: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="LAST SIGNAL 角色行走图生成器")
    parser.add_argument("--char", type=str, help="生成单个角色 (kai/oracle/joker)")
    parser.add_argument("--dir", type=str, help="生成单方向 (down/left/right/up)")
    parser.add_argument("--sheet", action="store_true", help="生成后拼合参考图")
    args = parser.parse_args()

    print("=" * 50)
    print("🎮 LAST SIGNAL - 角色行走图生成")
    print(f"   输出: {OUTPUT_DIR}")
    print(f"   尺寸: {SPRITE_SIZE}×{SPRITE_SIZE}")
    print("=" * 50)

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

    # 生成参考图
    if args.sheet:
        print(f"\n{'='*50}")
        print("📋 拼合参考图:")
        for char_id in chars:
            for d in (dirs or list(DIRECTIONS.keys())):
                gen_walk_sheet(char_id, d)

    print(f"\n{'='*50}")
    print(f"✅ 成功: {total_ok}  ❌ 失败: {total_fail}")
    print(f"📁 {OUTPUT_DIR}")

    # 生成场景配置提示
    print(f"\n{'='*50}")
    print("💡 提示: 在 index.html 的 SCENES 中添加角色配置:")
    print("""
    characters: [{
      id: 'kai',
      sprite: 'sprites/kai',
      x: 0.5, y: 0.7,  // 归一化坐标
      direction: 'down',
      speed: 0.15,
      depth: 0.6,       // Y轴深度基准
    }]
    """)


if __name__ == "__main__":
    main()
