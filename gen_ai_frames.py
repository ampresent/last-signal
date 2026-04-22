#!/usr/bin/env python3
"""
LAST SIGNAL — AI 动画帧生成器 v2 (极致版)

策略：
1. 用 Pollinations.AI img2img 生成 N 个关键帧 (AI 生成的画面变化)
2. 用 OpenCV 光流插值在关键帧之间生成中间帧
3. 形成真正流畅的动画序列，帧间过渡自然
4. 支持无缝循环 (最后一帧平滑过渡回第一帧)

输出：每场景 12 帧 (4关键帧 × 3插值帧)
"""

import urllib.request
import urllib.parse
import os
import sys
import time
import shutil

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("❌ 需要 OpenCV: pip install opencv-python-headless numpy")
    sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://image.pollinations.ai/prompt/"
W, H = 960, 640
SEED = 2087

# ============================================================
# 关键帧定义
# 每个场景 4 个关键帧，描述一个完整的动画循环
# 帧间变化尽可能微妙，保持场景一致性
# ============================================================

SCENE_KEYFRAMES = {
    "bg_apartment": {
        "base": (
            "pixel art cyberpunk apartment room, 16-bit retro game aesthetic, "
            "cyberpunk noir, limited color palette, dark moody atmosphere, "
            "messy desk with old computer terminal, rain on window, dim ceiling light, "
            "posters on wall, worn furniture, coffee mug, cables everywhere, "
            "game background art, no characters"
        ),
        "keyframes": [
            "",  # K0: base (原始)
            "bright green CRT glow illuminating the entire desk area, terminal screen fully lit, "
            "green light reflecting on nearby walls and ceiling, room looks noticeably brighter from screen",  # K1: 终端大亮
            "heavy rain streaks streaming down the window, water droplets thick and visible, "
            "ceiling light off the room is darker, only window light and screen glow visible",  # K2: 雨大+灯灭
            "ceiling light flickering warm orange, terminal screen dark and powered off, "
            "room lit mainly by overhead warm light, shadows deeper, cozy warm tones",  # K3: 灯亮终端灭
        ],
    },
    "bg_street": {
        "base": (
            "pixel art rainy cyberpunk street at night, 16-bit retro game aesthetic, "
            "cyberpunk noir, dark moody atmosphere, rain-soaked, neon accents, "
            "wet asphalt reflecting neon signs, tall buildings with glowing windows, "
            "puddles with reflections, fog, steam from grates, game background art"
        ),
        "keyframes": [
            "",
            "neon reflections on wet ground slightly more vivid and colorful",
            "heavier rain streaks visible, deeper puddle reflections, more mist",
            "some neon signs dimmer, overall darker, flickering street light",
        ],
    },
    "bg_bar": {
        "base": (
            "pixel art interior of dark cyberpunk bar, 16-bit retro game aesthetic, "
            "cyberpunk noir, neon accents, counter with bottles, dim purple and red neon, "
            "stools, smoke haze, barkeeper area, moody atmosphere, game background art"
        ),
        "keyframes": [
            "",
            "purple and red neon glowing brighter, more colorful light on bottles",
            "thicker smoke haze drifting across room, deeper shadows",
            "one neon sign slightly dimmer, bar area moodier, warm amber tones",
        ],
    },
    "bg_alley": {
        "base": (
            "pixel art dark narrow cyberpunk back alley, 16-bit retro game aesthetic, "
            "cyberpunk noir, rain-soaked, neon accents, overflowing dumpsters, graffiti, "
            "flickering neon light, puddles, fire escape, cables overhead, grim atmosphere, "
            "game background art"
        ),
        "keyframes": [
            "",
            "flickering neon casting stronger green glow on wet walls",
            "more rain dripping, heavier puddle reflections, steam rising",
            "neon almost off, darker atmosphere, faint emergency red light",
        ],
    },
    "bg_tower_exterior": {
        "base": (
            "pixel art corporate tower exterior at night, 16-bit retro game aesthetic, "
            "cyberpunk noir, dark moody atmosphere, rain-soaked, "
            "imposing dark glass building, rain, security booth, lobby lights, "
            "game background art"
        ),
        "keyframes": [
            "",
            "lobby lights inside slightly brighter, glass reflecting more sky",
            "heavier rainfall, more visible rain streaks on glass facade",
            "one lobby light off, slightly darker overall, moody atmosphere",
        ],
    },
    "bg_server_room": {
        "base": (
            "pixel art corporate server room, 16-bit retro game aesthetic, "
            "cyberpunk noir, server racks with blinking lights blue and green, "
            "cables, fluorescent lighting, terminal screens, sterile interior, "
            "game background art"
        ),
        "keyframes": [
            "",
            "server LEDs cycling faster, more green blinking lights visible",
            "terminal screens brighter with scrolling data, blue glow stronger",
            "fluorescent light flickering, slightly darker corners, electrical hum vibe",
        ],
    },
    "bg_rooftop": {
        "base": (
            "pixel art rainy cyberpunk rooftop at night, 16-bit retro game aesthetic, "
            "cyberpunk noir, rain-soaked, city skyline with neon lights, antenna tower, "
            "puddles on concrete, wind and rain, fog, dramatic atmosphere, "
            "game background art"
        ),
        "keyframes": [
            "",
            "city skyline neon lights slightly more vivid in distance",
            "intense rain, heavier downpour, more water streaming on ground",
            "lightning flash illuminating skyline, brighter clouds then fading",
        ],
    },
    "bg_office": {
        "base": (
            "pixel art cyberpunk corporate office, 16-bit retro game aesthetic, "
            "cyberpunk noir, large desk with holographic display, executive chair, "
            "city view through windows, dim lighting, rain on windows, "
            "game background art"
        ),
        "keyframes": [
            "",
            "holographic display glowing brighter, more blue light on desk surface",
            "more rain on windows, water droplets visible, cooler tones",
            "desk lamp flickering, holographic display glitching, warmer amber tones",
        ],
    },
}


def download_image(prompt, filepath, seed=SEED):
    """从 Pollinations.AI 下载图片"""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        print(f"    ⏭️  已有")
        return filepath

    encoded = urllib.parse.quote(prompt)
    url = f"{BASE_URL}{encoded}?width={W}&height={H}&seed={seed}&model=flux&nologo=true"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"    ✅ {len(data)//1024}KB")
            return filepath
    except Exception as e:
        print(f"    ❌ {e}")
        return None


def img2img(input_path, prompt, output_path, seed=SEED):
    """Pollinations img2img POST"""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"    ⏭️  已有")
        return output_path

    encoded = urllib.parse.quote(prompt)
    url = f"{BASE_URL}{encoded}?width={W}&height={H}&seed={seed}&model=flux&nologo=true"

    boundary = "----FormBoundary7MA4YWxk"
    with open(input_path, "rb") as f:
        image_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="base.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()

    try:
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(output_path, "wb") as f:
                f.write(data)
            print(f"    ✅ {len(data)//1024}KB")
            return output_path
    except Exception as e:
        print(f"    ❌ {e}")
        return None


def interpolate_frames(frame_a, frame_b, num_interp):
    """
    在两帧之间用光流插值生成中间帧。
    使用 Farneback 光流 + 反向映射进行像素级插值。
    """
    if num_interp == 0:
        return []

    a = frame_a.astype(np.float32)
    b = frame_b.astype(np.float32)

    # 计算前向光流 (a → b)
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        gray_a, gray_b, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
    )

    h, w = frame_a.shape[:2]
    result_frames = []

    for i in range(1, num_interp + 1):
        t = i / (num_interp + 1)

        # 计算插值位置的光流
        flow_t = flow * t

        # 创建映射网格
        map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32),
                                    np.arange(h, dtype=np.float32))
        map_x = map_x + flow_t[:, :, 0]
        map_y = map_y + flow_t[:, :, 1]

        # 用光流映射 warp frame_a
        warped_a = cv2.remap(a, map_x, map_y, cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)

        # 反向光流 warp frame_b
        flow_rev = cv2.calcOpticalFlowFarneback(
            gray_b, gray_a, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )
        flow_rev_t = flow_rev * (1 - t)
        map_x_rev = np.meshgrid(np.arange(w, dtype=np.float32),
                                 np.arange(h, dtype=np.float32))[0] + flow_rev_t[:, :, 0]
        map_y_rev = np.meshgrid(np.arange(w, dtype=np.float32),
                                 np.arange(h, dtype=np.float32))[1] + flow_rev_t[:, :, 1]
        warped_b = cv2.remap(b, map_x_rev, map_y_rev, cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)

        # 双向融合：权重混合
        alpha = t
        interp = warped_a * (1 - alpha) + warped_b * alpha

        # 处理遮挡区域（光流映射后可能出现黑色空洞）
        # 用简单线性混合作为 fallback
        linear_blend = a * (1 - t) + b * t
        mask_a = (np.sum(np.abs(warped_a - a), axis=2, keepdims=True) > 30).astype(np.float32)
        interp = interp * mask_a + linear_blend * (1 - mask_a)

        result_frames.append(np.clip(interp, 0, 255).astype(np.uint8))

    return result_frames


def generate_scene_animation(scene_name, config):
    """为一个场景生成完整动画序列"""
    print(f"\n🎬 {scene_name}")

    base_prompt = config["base"]
    keyframe_prompts = config["keyframes"]
    num_keyframes = len(keyframe_prompts)
    num_interp = 2  # 关键帧之间插值 2 帧
    total_frames = num_keyframes + (num_keyframes - 1) * num_interp
    # 加上循环回第一帧的插值
    total_with_loop = total_frames + num_interp

    print(f"  关键帧: {num_keyframes}, 插值: {num_interp}/对, 总帧: {total_with_loop}")

    # Step 1: 生成基础图 (K0)
    k0_path = os.path.join(OUTPUT_DIR, f"{scene_name}_k0.png")
    if not os.path.exists(k0_path) or os.path.getsize(k0_path) < 10000:
        print(f"  📷 生成基础图 K0...")
        download_image(base_prompt, k0_path)
        time.sleep(3)
    else:
        print(f"  📷 基础图 K0 已有")

    # Step 2: 生成关键帧 K1, K2, K3 (img2img from K0)
    keyframe_paths = [k0_path]
    for i in range(1, num_keyframes):
        ki_path = os.path.join(OUTPUT_DIR, f"{scene_name}_k{i}.png")
        if not os.path.exists(ki_path) or os.path.getsize(ki_path) < 10000:
            prompt = f"{base_prompt}, {keyframe_prompts[i]}"
            print(f"  🎨 生成关键帧 K{i} (img2img)...")
            img2img(k0_path, prompt, ki_path)
            time.sleep(3)
        else:
            print(f"  🎨 关键帧 K{i} 已有")
        keyframe_paths.append(ki_path)

    # Step 3: 读取所有关键帧
    keyframes = []
    for p in keyframe_paths:
        img = cv2.imread(p)
        if img is not None:
            # 统一尺寸
            if img.shape[1] != W or img.shape[0] != H:
                img = cv2.resize(img, (W, H))
            keyframes.append(img)
        else:
            print(f"  ❌ 无法读取: {p}")

    if len(keyframes) < 2:
        print(f"  ❌ 关键帧不足，无法插值")
        return 0

    # Step 4: 光流插值生成所有帧
    print(f"  🔄 光流插值生成动画...")
    all_frames = []

    for ki in range(len(keyframes)):
        all_frames.append(keyframes[ki])

        if ki < len(keyframes) - 1:
            # 在当前关键帧和下一个之间插值
            interp = interpolate_frames(keyframes[ki], keyframes[ki + 1], num_interp)
            all_frames.extend(interp)
        else:
            # 最后一个关键帧 → 循环回第一个
            interp = interpolate_frames(keyframes[ki], keyframes[0], num_interp)
            all_frames.extend(interp)

    # Step 5: 保存所有帧
    print(f"  💾 保存 {len(all_frames)} 帧...")
    saved = 0
    for i, frame in enumerate(all_frames):
        out_path = os.path.join(OUTPUT_DIR, f"{scene_name}_f{i}.png")
        cv2.imwrite(out_path, frame)
        saved += 1

    # Step 6: 分析质量
    print(f"  📊 帧间差异:")
    for i in range(1, min(len(all_frames), 15)):
        diff = np.mean(cv2.absdiff(all_frames[0], all_frames[i]))
        bar = "█" * int(diff / 2) + "░" * max(0, 20 - int(diff / 2))
        level = "微妙" if diff < 10 else "适中" if diff < 20 else "可见"
        print(f"     f0↔f{i:2d}: {diff:5.1f} {bar} [{level}]")

    # 循环质量
    if len(all_frames) > 1:
        loop_diff = np.mean(cv2.absdiff(all_frames[0], all_frames[-1]))
        print(f"     循环:   f0↔f{len(all_frames)-1}: {loop_diff:.1f}")

    return saved


def main():
    print("=" * 60)
    print("🎬 LAST SIGNAL — AI 动画帧生成器 v2 (极致版)")
    print("   Pollinations img2img 关键帧 + OpenCV 光流插值")
    print("=" * 60)

    total_ok = 0
    total_fail = 0

    for scene_name, config in SCENE_KEYFRAMES.items():
        got = generate_scene_animation(scene_name, config)
        total_ok += got
        total_fail += max(0, 15 - got)

    print(f"\n{'='*60}")
    print(f"✅ 总帧数: {total_ok}")
    print(f"📁 {OUTPUT_DIR}")
    print(f"\n💡 每场景 {total_ok // len(SCENE_KEYFRAMES)} 帧 (含光流插值 + 循环)")


if __name__ == "__main__":
    main()
