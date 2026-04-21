#!/usr/bin/env python3
"""
LAST SIGNAL — AI img2img 动画帧生成器
使用 Pollinations.AI 的 img2img POST 端点，从基础场景图生成连贯动画帧。

原理：将基础图作为 init image 输入，配合微调提示词生成略有变化的后续帧。
帧间差异由 AI 控制，可实现灯光变化、雨势增强、人物微动等效果。

与 VFX 引擎配合使用：
  - VFX 引擎：实时粒子效果（雨滴、雾气、霓虹、扫描线）
  - AI 帧：场景本身的微妙变化（灯光、氛围、人物位置）
  - 两者叠加 = 沉浸感拉满

依赖：仅标准库 + opencv-python-headless (可选，用于帧分析)
"""

import urllib.request
import urllib.parse
import os
import sys
import time
import json

# 可选：OpenCV 用于帧分析
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://image.pollinations.ai/prompt/"
W, H = 960, 640
SEED = 2087

# ============================================================
# 场景动画定义
#
# 每个场景定义：
#   base_prompt: 基础提示词（用于生成 f0）
#   variations:  5 帧的提示词微调（f0-f4）
#     - "" 表示与基础提示词相同
#     - 非空字符串会追加到基础提示词后
#
# 变化幅度控制：
#   - 微妙：灯光色温变化、亮度微调
#   - 中等：天气强度变化、雾气浓度
#   - 明显：人物位置、物体状态
# ============================================================

SCENE_ANIMATIONS = {
    "bg_apartment": {
        "base_prompt": (
            "A small dark cyberpunk apartment room, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, "
            "messy desk with old computer terminal glowing green, rain on window, dim ceiling light, "
            "posters on wall, worn furniture, coffee mug, cables everywhere, "
            "top-down slight perspective adventure game view, no characters, game background art"
        ),
        "variations": [
            "",  # f0: 原图
            "slightly brighter green terminal glow illuminating the desk",  # f1: 终端发光增强
            "more visible rain streaks on the window glass, wet window",    # f2: 雨变大
            "dimmer ambient light, one flickering light source",            # f3: 灯光闪烁
            "thin blue-gray haze floating through the room, subtle fog",    # f4: 薄雾
        ]
    },

    "bg_street": {
        "base_prompt": (
            "A rainy cyberpunk street at night, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, "
            "wet asphalt reflecting neon signs, tall buildings with glowing windows, street vendor stalls, "
            "puddles with reflections, distant flying vehicles, fog, steam from grates, alley entrance visible, "
            "game background art, adventure game scene"
        ),
        "variations": [
            "",
            "neon signs slightly brighter with pulsing glow, enhanced reflections",
            "heavy rain with more visible rain streaks, deeper puddles",
            "some neon signs flickering, dimmer overall atmosphere",
            "thicker fog rolling between buildings, steam rising from grates",
        ]
    },

    "bg_bar": {
        "base_prompt": (
            "Interior of a dark cyberpunk bar called The Rust, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, neon accents, "
            "counter with bottles, dim neon lighting in purple and red, stools, "
            "mysterious patrons in shadows, jukebox, smoke haze, barkeeper behind counter, "
            "moody atmosphere, game background art, adventure game scene"
        ),
        "variations": [
            "",
            "purple and red neon lights pulsing brighter, enhanced glow on bottles",
            "more smoke haze drifting across the room, thicker atmosphere",
            "one neon sign flickering, slightly darker overall, strobing light",
            "subtle blue fog mixing with smoke, mysterious haze",
        ]
    },

    "bg_alley": {
        "base_prompt": (
            "A dark narrow cyberpunk back alley, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, "
            "overflowing dumpsters, graffiti on walls, flickering neon light, puddles, fire escape ladder, "
            "cables overhead, trash scattered, shadowy corner, rain dripping, grim atmosphere, "
            "game background art, adventure game scene"
        ),
        "variations": [
            "",
            "flickering neon sign brighter, casting more green light on wet walls",
            "heavier rain dripping from fire escape, deeper puddle reflections",
            "neon sign cutting out momentarily, almost complete darkness then relit",
            "mist rising from puddles, steam venting from pipe, foggy atmosphere",
        ]
    },

    "bg_tower_exterior": {
        "base_prompt": (
            "Front of a massive corporate tower at night, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, "
            "imposing dark glass building, rain, security booth, bright lobby lights inside, "
            "corporate logo, sleek modern architecture contrasting with dirty street, "
            "game background art, adventure game scene"
        ),
        "variations": [
            "",
            "lobby lights inside slightly brighter, glass reflecting more light",
            "heavier rainfall, more visible rain streaks on glass facade",
            "one lobby light flickering, security booth light dimming",
            "low fog around building base, mist obscuring lower floors",
        ]
    },

    "bg_server_room": {
        "base_prompt": (
            "A corporate server room, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, neon accents, "
            "rows of server racks with blinking lights in blue and green, cables everywhere, "
            "cold fluorescent lighting, terminal screens, humming machines, sterile corporate interior, "
            "locked door visible, game background art, adventure game scene"
        ),
        "variations": [
            "",
            "server rack LEDs cycling faster, more green and blue blinking lights",
            "terminal screens showing scrolling data, brighter screen glow",
            "one fluorescent light flickering, slightly darker corners",
            "thin electrical haze near server racks, heat shimmer effect",
        ]
    },

    "bg_rooftop": {
        "base_prompt": (
            "A rainy cyberpunk building rooftop at night, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, "
            "city skyline with neon lights in background, antenna tower, puddles on concrete, "
            "wind and rain, helicopter pad markings, edge railing, dramatic atmosphere, fog, "
            "game background art, adventure game scene"
        ),
        "variations": [
            "",
            "city skyline neon lights slightly brighter in distance",
            "intense rain and wind, heavier downpour, water streaming",
            "distant lightning flash illuminating the skyline momentarily",
            "thick fog rolling over rooftop edge, obscuring city below",
        ]
    },

    "bg_office": {
        "base_prompt": (
            "A cyberpunk corporate office, pixel art style, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, neon accents, "
            "large desk with holographic display, executive chair, city view through floor-to-ceiling windows, "
            "luxury meets decay, filing cabinets, security safe, dim lighting, rain on windows, "
            "game background art, adventure game scene"
        ),
        "variations": [
            "",
            "holographic display glowing brighter, casting blue light on desk",
            "more rain on windows, water droplets streaking down glass",
            "desk lamp flickering, holographic display glitching briefly",
            "fog outside windows, city lights blurred through mist",
        ]
    },
}


def generate_base_image(scene_name, prompt):
    """生成基础场景图 (f0)"""
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE_URL}{encoded}?width={W}&height={H}&seed={SEED}&model=flux&nologo=true"

    filepath = os.path.join(OUTPUT_DIR, f"{scene_name}_f0.png")
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        print(f"  ⏭️  f0 已有")
        return filepath

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"  ✅ f0 ({len(data)//1024}KB)")
            return filepath
    except Exception as e:
        print(f"  ❌ f0: {e}")
        return None


def generate_variation(scene_name, frame_idx, base_image_path, base_prompt, variation_suffix):
    """
    使用 img2img 生成一帧变体。
    将 base_image 作为 init image，配合微调提示词。
    """
    if not variation_suffix:
        # f0 就是基础图，复制即可
        src = base_image_path
        dst = os.path.join(OUTPUT_DIR, f"{scene_name}_f{frame_idx}.png")
        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            print(f"  ⏭️  f{frame_idx} 已有")
            return True
        if src and os.path.exists(src):
            import shutil
            shutil.copy2(src, dst)
            print(f"  📋 f{frame_idx} (复制基础图)")
            return True
        return False

    filepath = os.path.join(OUTPUT_DIR, f"{scene_name}_f{frame_idx}.png")
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        print(f"  ⏭️  f{frame_idx} 已有")
        return True

    if not base_image_path or not os.path.exists(base_image_path):
        print(f"  ❌ f{frame_idx}: 基础图不存在")
        return False

    # 构建微调提示词
    full_prompt = f"{base_prompt}, {variation_suffix}"
    encoded = urllib.parse.quote(full_prompt)
    # 使用相同 seed 保持一致性，但提示词不同
    url = f"{BASE_URL}{encoded}?width={W}&height={H}&seed={SEED}&model=flux&nologo=true"

    try:
        # 以 base_image 作为 init image 发送 POST
        import mimetypes
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

        with open(base_image_path, "rb") as f:
            image_data = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="base.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"  ✅ f{frame_idx} ({len(data)//1024}KB)")
            return True

    except Exception as e:
        print(f"  ❌ f{frame_idx}: {e}")
        return False


def analyze_frames(scene_name, num_frames=5):
    """分析帧间差异（需要 OpenCV）"""
    if not HAS_CV2:
        return

    frames = []
    for i in range(num_frames):
        path = os.path.join(OUTPUT_DIR, f"{scene_name}_f{i}.png")
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                frames.append(img)

    if len(frames) < 2:
        return

    print(f"  📊 帧间差异分析:")
    for i in range(1, len(frames)):
        diff = np.mean(cv2.absdiff(frames[0], frames[i]))
        bar = "█" * int(diff / 2) + "░" * (25 - int(diff / 2))
        level = "微妙" if diff < 10 else "适中" if diff < 25 else "明显"
        print(f"     f0↔f{i}: {diff:5.1f} {bar} [{level}]")


def process_scene(scene_name, config):
    """处理单个场景：生成基础图 + 5 帧动画"""
    print(f"\n📁 {scene_name}")

    # 1. 生成基础图
    base_path = generate_base_image(scene_name, config["base_prompt"])
    time.sleep(2)

    # 2. 生成每帧变体
    variations = config.get("variations", [""] * 5)
    success = 0
    for i, var in enumerate(variations):
        if generate_variation(scene_name, i, base_path, config["base_prompt"], var):
            success += 1
        time.sleep(3)  # 避免请求过快

    # 3. 分析帧间差异
    analyze_frames(scene_name)

    return success


def main():
    mode = "AI img2img 帧生成"
    print("=" * 60)
    print(f"🎬 LAST SIGNAL — {mode}")
    print(f"   使用 Pollinations.AI img2img POST 端点")
    print(f"   每场景 5 帧 (f0基础图 + f1-f4变体)")
    print("=" * 60)

    ok, fail = 0, 0

    for scene_name, config in SCENE_ANIMATIONS.items():
        got = process_scene(scene_name, config)
        ok += got
        fail += (5 - got)

    print(f"\n{'='*60}")
    print(f"✅ 成功: {ok}  ❌ 失败: {fail}")
    print(f"📁 {OUTPUT_DIR}")

    if not HAS_CV2:
        print(f"\n💡 安装 opencv-python-headless 可启用帧差异分析:")
        print(f"   pip install opencv-python-headless numpy")


if __name__ == "__main__":
    main()
