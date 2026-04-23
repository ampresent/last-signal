#!/usr/bin/env python3
"""
LAST SIGNAL - 角色行走图生成器 v2 (抠图 + 程序化动画)

新流程:
  1. 生成 1 张高质量站立图 (Pollinations)
  2. rembg 抠图 → RGBA 透明背景
  3. 程序化生成 8 帧行走动画 (位移/缩放/倾斜)
     → 帧间零抖动，完全一致的角色外观

用法:
    python3 gen_character_sprites.py              # 全部角色
    python3 gen_character_sprites.py --char kai   # 单个角色
    python3 gen_character_sprites.py --char kai --dir down
    python3 gen_character_sprites.py --migrate     # 旧版迁移: 对已有精灵抠图
"""
import urllib.request
import urllib.parse
import os
import sys
import time
import argparse
import math

from PIL import Image, ImageOps, ImageFilter
import numpy as np

OUTPUT_DIR = "assets/sprites"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"

# ── 基础风格 (单帧站立图) ──
SPRITE_STYLE = (
    "pixel art character sprite, 16-bit retro game, cyberpunk noir style, "
    "single character standing pose, full body, centered in frame, "
    "clean pixel art, limited color palette, "
    "transparent background, isolated character, no text, no labels, "
    "game character asset, high quality"
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
    "left":  {"facing": "facing left, side view, left profile",                      "seed_offset": 100},
    "right": {"facing": "facing right, side view, right profile",                    "seed_offset": 200},
    "up":    {"facing": "facing away from viewer, back view",                        "seed_offset": 300},
}

FRAME_W = 128
FRAME_H = 128
WALK_FRAMES = 8           # 8 帧行走循环 (比 4 帧流畅一倍)
SEED_BASE = 2087
SPRITE_GEN_SIZE = 256     # 生成时用 256×256，质量更高，再缩小到 128×128


# ══════════════════════════════════════════════════════════════
# Step 1: 下载生成
# ══════════════════════════════════════════════════════════════

def download(url, filepath, timeout=180):
    """下载图片，跳过已存在的文件"""
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


def gen_base_image(char_id, direction):
    """生成单方向的站立图 (256×256)"""
    char = CHARACTERS[char_id]
    dinfo = DIRECTIONS[direction]

    prompt = (
        f"{SPRITE_STYLE}, "
        f"{char['base_prompt']}, "
        f"{dinfo['facing']}, "
        f"colors: {char['palette']}"
    )

    seed = SEED_BASE + dinfo["seed_offset"]
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={SPRITE_GEN_SIZE}&height={SPRITE_GEN_SIZE}&seed={seed}&model=flux&nologo=true"

    raw_path = os.path.join(OUTPUT_DIR, f"raw_{char_id}_{direction}.png")
    ok = download(url, raw_path)
    return ok, raw_path


# ══════════════════════════════════════════════════════════════
# Step 2: 抠图 (rembg)
# ══════════════════════════════════════════════════════════════

def remove_bg(input_path, output_path):
    """使用 rembg 去除背景 → RGBA 透明图"""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
        print(f"   ⏭️  抠图已有: {os.path.basename(output_path)}")
        return True

    try:
        from rembg import remove

        with open(input_path, "rb") as f:
            input_data = f.read()

        output_data = remove(input_data)

        with open(output_path, "wb") as f:
            f.write(output_data)

        size_kb = len(output_data) // 1024
        print(f"   🎭 抠图完成: {os.path.basename(output_path)} ({size_kb}KB)")
        return True
    except Exception as e:
        print(f"   ❌ 抠图失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# Step 3: 程序化行走动画
# ══════════════════════════════════════════════════════════════

def generate_walk_frames(base_rgba, num_frames=8):
    """
    从一张 RGBA 站立图，程序化生成 N 帧行走动画。

    变换策略:
      - 垂直弹跳 (body bob): 身体上下起伏
      - 水平摇摆 (sway): 身体左右微晃
      - 腿部模拟: 通过底部区域的剪切错位模拟迈步
      - 轻微缩放: 呼吸感

    返回: list of PIL.Image (RGBA, FRAME_W × FRAME_H)
    """
    frames = []

    # 缩放到目标帧大小
    base = base_rgba.resize((FRAME_W, FRAME_H), Image.LANCZOS)

    for i in range(num_frames):
        t = i / num_frames  # 0.0 ~ 1.0 (一个完整步态周期)
        phase = t * 2 * math.pi

        frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))

        # ── 1. 垂直弹跳 ──
        # 走路时身体上下起伏，每步两次高点 (双脚离地时最高)
        bob = int(round(-2.5 * abs(math.sin(phase * 2))))  # 0 ~ -2.5 px

        # ── 2. 水平摇摆 ──
        sway = int(round(1.5 * math.sin(phase)))  # -1.5 ~ 1.5 px

        # ── 3. 轻微缩放 (呼吸感) ──
        scale_factor = 1.0 + 0.008 * math.sin(phase * 2)

        # ── 4. 腿部模拟: 底部区域错位 ──
        # 将角色图分为上下两部分:
        #   上半身 (60%): 整体平移
        #   下半身 (40%): 额外的左右错位模拟迈步
        leg_offset = int(round(3.0 * math.sin(phase)))  # -3 ~ 3 px

        # ── 应用变换 ──
        # 先做缩放
        sw = int(FRAME_W * scale_factor)
        sh = int(FRAME_H * scale_factor)
        scaled = base.resize((sw, sh), Image.LANCZOS)

        # 裁剪回原尺寸 (居中)
        cx, cy = sw // 2, sh // 2
        scaled = scaled.crop((cx - FRAME_W // 2, cy - FRAME_H // 2,
                              cx + FRAME_W // 2, cy + FRAME_H // 2))

        # 分离上下半身
        split_y = int(FRAME_H * 0.55)  # 55% 处分割 (腰部附近)
        upper = scaled.crop((0, 0, FRAME_W, split_y))
        lower = scaled.crop((0, split_y, FRAME_W, FRAME_H))

        # 下半身额外错位
        lower_shifted = Image.new("RGBA", (FRAME_W, FRAME_H - split_y), (0, 0, 0, 0))
        lower_shifted.paste(lower, (leg_offset, 0))

        # 合成: 上半身 + 下半身
        body = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        body.paste(upper, (sway, bob))
        body.paste(lower_shifted, (sway, split_y + bob))

        # ── 5. 脚部阴影 (可选) ──
        # 在底部画一个微弱的椭圆阴影
        shadow = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(shadow)
        shadow_y = FRAME_H - 6
        shadow_w = int(FRAME_W * 0.35)
        draw.ellipse(
            [FRAME_W // 2 - shadow_w, shadow_y - 2,
             FRAME_W // 2 + shadow_w, shadow_y + 2],
            fill=(0, 0, 0, 50)
        )

        frame = Image.alpha_composite(frame, shadow)
        frame = Image.alpha_composite(frame, body)

        # ── 6. 站立帧修正 ──
        # 第 0 帧和第 4 帧应该是"站立"姿态，减少抖动感
        if i == 0 or i == num_frames // 2:
            frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
            frame = Image.alpha_composite(frame, shadow)
            frame.paste(scaled, (0, 0), scaled)

        frames.append(frame)

    return frames


# ══════════════════════════════════════════════════════════════
# 完整流水线
# ══════════════════════════════════════════════════════════════

def process_character(char_id, directions=None, force=False, num_frames=8):
    """处理一个角色的完整流程"""
    char = CHARACTERS[char_id]
    dirs = directions or list(DIRECTIONS.keys())

    print(f"\n👤 {char['name']} ({char_id}):")
    ok, fail = 0, 0

    for d in dirs:
        print(f"\n   ── 方向: {d} ──")

        raw_path = os.path.join(OUTPUT_DIR, f"raw_{char_id}_{d}.png")
        cutout_path = os.path.join(OUTPUT_DIR, f"cutout_{char_id}_{d}.png")

        # Step 1: 生成基础图
        if force or not os.path.exists(raw_path) or os.path.getsize(raw_path) < 5000:
            gen_ok, _ = gen_base_image(char_id, d)
            if not gen_ok:
                fail += num_frames
                time.sleep(2)
                continue
        else:
            print(f"   ⏭️  基础图已有: {os.path.basename(raw_path)}")

        # Step 2: 抠图
        if force or not os.path.exists(cutout_path) or os.path.getsize(cutout_path) < 5000:
            mat_ok = remove_bg(raw_path, cutout_path)
            if not mat_ok:
                fail += num_frames
                continue
        else:
            print(f"   ⏭️  抠图已有: {os.path.basename(cutout_path)}")

        # Step 3: 程序化行走动画
        try:
            base_img = Image.open(cutout_path).convert("RGBA")
            frames = generate_walk_frames(base_img, num_frames=num_frames)

            for fi, frame_img in enumerate(frames):
                out_path = os.path.join(OUTPUT_DIR, f"{char_id}_{d}_f{fi}.png")
                frame_img.save(out_path)

            print(f"   🚶 生成 {num_frames} 帧行走动画 ✓")
            ok += num_frames
        except Exception as e:
            print(f"   ❌ 行走动画生成失败: {e}")
            fail += num_frames

        time.sleep(2)  # 避免 API 速率限制

    return ok, fail


def migrate_existing():
    """对已有精灵图执行抠图 (不需要重新生成)"""
    print("=" * 55)
    print("🎭 迁移模式: 对已有精灵图执行抠图")
    print("=" * 55)

    # 找到所有 raw_ 文件
    raw_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("raw_") and f.endswith(".png")]
    if not raw_files:
        print("   ❌ 没有找到 raw_ 文件")
        return

    for raw_file in sorted(raw_files):
        # raw_kai_down.png → cutout_kai_down.png
        base_name = raw_file[4:]  # 去掉 "raw_"
        cutout_file = f"cutout_{base_name}"
        raw_path = os.path.join(OUTPUT_DIR, raw_file)
        cutout_path = os.path.join(OUTPUT_DIR, cutout_file)

        if os.path.exists(cutout_path) and os.path.getsize(cutout_path) > 5000:
            print(f"   ⏭️  {cutout_file} 已有")
            continue

        print(f"   🎭 抠图: {raw_file}")
        remove_bg(raw_path, cutout_path)

    print("\n✅ 抠图完成。运行不带 --migrate 重新生成行走帧。")


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LAST SIGNAL 角色行走图生成器 v2")
    parser.add_argument("--char", type=str, help="生成单个角色 (kai/oracle/joker)")
    parser.add_argument("--dir", type=str, help="生成单方向 (down/left/right/up)")
    parser.add_argument("--force", action="store_true", help="强制重新生成")
    parser.add_argument("--migrate", action="store_true", help="对已有精灵抠图 (不重新生成)")
    parser.add_argument("--frames", type=int, default=WALK_FRAMES, help=f"行走帧数 (默认 {WALK_FRAMES})")
    args = parser.parse_args()

    walk_frames = args.frames

    if args.migrate:
        migrate_existing()
        return

    print("=" * 55)
    print("🎮 LAST SIGNAL - 角色行走图生成器 v2")
    print(f"   输出: {OUTPUT_DIR}")
    print(f"   流程: 生成 → 抠图(rembg) → 程序化行走动画({walk_frames}帧)")
    print("=" * 55)

    chars = [args.char] if args.char else list(CHARACTERS.keys())
    dirs = [args.dir] if args.dir else None

    total_ok, total_fail = 0, 0

    for char_id in chars:
        if char_id not in CHARACTERS:
            print(f"❌ 未知角色: {char_id} (可选: {', '.join(CHARACTERS.keys())})")
            continue
        ok, fail = process_character(char_id, dirs, force=args.force, num_frames=walk_frames)
        total_ok += ok
        total_fail += fail

    print(f"\n{'='*55}")
    print(f"✅ 成功: {total_ok} 帧  ❌ 失败: {total_fail} 帧")
    print(f"📁 {OUTPUT_DIR}")

    # 统计
    cutouts = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("cutout_")]
    sprites = [f for f in os.listdir(OUTPUT_DIR)
               if f.endswith('.png') and not f.startswith('raw_') and not f.startswith('cutout_') and not f.startswith('sheet_')]
    print(f"\n📋 抠图: {len(cutouts)} 张  |  行走帧: {len(sprites)} 张")


if __name__ == "__main__":
    main()
