#!/usr/bin/env python3
"""
gen_depth_lighting.py — Depth-based lighting renderer for ALL scenes

Replaces img2img strategy entirely. Uses Depth-Anything-V2-Large for depth
estimation + programmatic 2D depth-based lighting per scene.

Usage:
    python3 gen_depth_lighting.py                    # all scenes
    python3 gen_depth_lighting.py --scene apartment   # single scene
    python3 gen_depth_lighting.py --lighting-only     # skip depth (reuse cache)
    python3 gen_depth_lighting.py --depth-only        # depth maps only
"""

import sys
import os
import time
import argparse
import math
from pathlib import Path

import numpy as np
import cv2
import torch

# ── Constants ──────────────────────────────────────────────────────
ASSETS_DIR = "assets"
NUM_FRAMES = 12
SHADOW_STEPS = 64
AMBIENT = 0.02  # 深夜最低环境光

# ── HuggingFace Mirror ────────────────────────────────────────────
HF_MODEL = "depth-anything/Depth-Anything-V2-Large-hf"
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT

# ── Phase Functions (整数倍频率，完美循环) ─────────────────────────

def _steady(frame_idx, num_frames):
    """恒定光。"""
    return 0.5

def _pulse_slow(frame_idx, num_frames):
    """缓慢脉冲，模拟呼吸/闪烁。"""
    t = 2 * math.pi * frame_idx / num_frames
    return max(0.0, min(1.0, 0.5 + 0.5 * math.sin(t * 1.0)))

def _pulse_medium(frame_idx, num_frames):
    """中速脉冲。"""
    t = 2 * math.pi * frame_idx / num_frames
    return max(0.0, min(1.0, 0.5 + 0.5 * math.sin(t * 2.0)))

def _irregular_car(frame_idx, num_frames):
    """车灯：不规则扫过 + soft threshold 渐入渐出。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = (0.5 + 0.5 * math.sin(t * 1.0 + 0.0)
         + 0.3 * math.sin(t * 3.0 + 1.2)
         + 0.2 * math.sin(t * 5.0 + 2.8))
    v = v / 1.0
    v = max(0.0, min(1.0, v))
    if v < 0.35:
        v *= 0.2
    elif v < 0.55:
        alpha = (v - 0.35) / 0.20
        alpha = alpha * alpha * (3 - 2 * alpha)
        v = 0.35 * 0.2 * (1 - alpha) + v * alpha
    return v

def _irregular_screen(frame_idx, num_frames):
    """屏幕/LED：不规则亮度闪烁。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = (0.5 + 0.5 * math.sin(t * 1.0 + 0.5)
         + 0.35 * math.sin(t * 2.0 + 1.7)
         + 0.25 * math.sin(t * 4.0 + 0.3)
         + 0.15 * math.sin(t * 6.0 + 3.1))
    v = v / 1.25
    return max(0.0, min(1.0, v))

def _moonlight_clouds(frame_idx, num_frames):
    """月光：云层遮挡。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = (0.5 + 0.5 * math.sin(t * 1.0 + 0.8)
         + 0.2 * math.sin(t * 2.0 + 2.0))
    v = v / 0.7
    return max(0.0, min(1.0, v))

def _flicker(frame_idx, num_frames):
    """不规则闪烁（霓虹/荧光灯）。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = (0.5 + 0.5 * math.sin(t * 2.0 + 0.3)
         + 0.4 * math.sin(t * 5.0 + 1.5)
         + 0.2 * math.sin(t * 7.0 + 2.7))
    v = v / 1.1
    return max(0.0, min(1.0, v))

def _lightning(frame_idx, num_frames):
    """闪电：大部分时间暗，偶尔闪一下。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = 0.5 + 0.5 * math.sin(t * 1.0 + 0.0)
    # 只在峰值附近闪亮
    if v > 0.85:
        return 1.0
    elif v > 0.7:
        return (v - 0.7) / 0.15
    return 0.0

def _phase_shift(func, offset):
    """给 phase function 加相位偏移。"""
    return lambda f, n: func(f + offset, n)


# ── Scene Light Source Definitions ─────────────────────────────────

SCENE_LIGHTS = {
    # ── 公寓：月光 + 车灯 + 屏幕 ──
    "apartment": {
        "base": "bg_apartment.png",
        "ambient": 0.02,
        "lights": [
            {"name": "moonlight", "pos": (120, 280),
             "color": [0.55, 0.65, 0.85], "intensity": (0.08, 0.22),
             "radius": 600, "phase": _moonlight_clouds},
            {"name": "car1", "pos": (60, 220),
             "color": [1.0, 0.92, 0.7], "intensity": (0.0, 0.2),
             "radius": 500, "phase": _irregular_car},
            {"name": "car2", "pos": (200, 180),
             "color": [1.0, 0.85, 0.6], "intensity": (0.0, 0.1),
             "radius": 450, "phase": _phase_shift(_irregular_car, 3)},
            {"name": "screen", "pos": (770, 320),
             "color": [0.15, 0.7, 0.25], "intensity": (0.03, 0.18),
             "radius": 280, "phase": _irregular_screen},
            {"name": "screen_flash", "pos": (750, 280),
             "color": [0.3, 0.85, 0.4], "intensity": (0.0, 0.08),
             "radius": 200, "phase": _phase_shift(_irregular_screen, 5)},
        ],
    },

    # ── 街道：霓虹 + 路灯 + 车灯 ──
    "street": {
        "base": "bg_street.png",
        "ambient": 0.03,
        "lights": [
            # 左侧大霓虹招牌（品红/粉）
            {"name": "neon_pink", "pos": (150, 150),
             "color": [1.0, 0.2, 0.5], "intensity": (0.08, 0.25),
             "radius": 400, "phase": _flicker},
            # 右侧霓虹（青色）
            {"name": "neon_cyan", "pos": (750, 200),
             "color": [0.1, 0.8, 0.9], "intensity": (0.06, 0.2),
             "radius": 350, "phase": _phase_shift(_flicker, 4)},
            # 远处车灯
            {"name": "car", "pos": (480, 500),
             "color": [1.0, 0.95, 0.8], "intensity": (0.0, 0.15),
             "radius": 500, "phase": _irregular_car},
            # 地面积水反射（来自多个霓虹）
            {"name": "puddle", "pos": (480, 580),
             "color": [0.3, 0.4, 0.6], "intensity": (0.02, 0.1),
             "radius": 300, "phase": _moonlight_clouds},
        ],
    },

    # ── 酒吧：紫红霓虹 + 琥珀吧台 ──
    "bar": {
        "base": "bg_bar.png",
        "ambient": 0.02,
        "lights": [
            # 紫色霓虹（左侧）
            {"name": "neon_purple", "pos": (200, 200),
             "color": [0.6, 0.1, 0.8], "intensity": (0.08, 0.28),
             "radius": 400, "phase": _pulse_slow},
            # 红色霓呐（右侧）
            {"name": "neon_red", "pos": (700, 180),
             "color": [0.9, 0.15, 0.1], "intensity": (0.06, 0.22),
             "radius": 350, "phase": _phase_shift(_pulse_slow, 4)},
            # 吧台背光（琥珀色）
            {"name": "bar_backlight", "pos": (480, 350),
             "color": [1.0, 0.7, 0.3], "intensity": (0.04, 0.15),
             "radius": 300, "phase": _steady},
            # 电视机闪烁
            {"name": "tv", "pos": (400, 250),
             "color": [0.4, 0.5, 0.7], "intensity": (0.02, 0.1),
             "radius": 200, "phase": _irregular_screen},
        ],
    },

    # ── 小巷：绿色霓虹 + 红色应急灯 ──
    "alley": {
        "base": "bg_alley.png",
        "ambient": 0.015,
        "lights": [
            # 绿色霓虹（闪烁）
            {"name": "neon_green", "pos": (400, 150),
             "color": [0.1, 0.9, 0.3], "intensity": (0.06, 0.3),
             "radius": 450, "phase": _flicker},
            # 红色应急灯
            {"name": "emergency", "pos": (150, 100),
             "color": [0.9, 0.1, 0.05], "intensity": (0.03, 0.12),
             "radius": 350, "phase": _pulse_medium},
            # 远处街灯漏光
            {"name": "street_leak", "pos": (850, 400),
             "color": [0.8, 0.75, 0.6], "intensity": (0.02, 0.08),
             "radius": 300, "phase": _steady},
        ],
    },

    # ── 塔楼外部：大厅灯光 + 建筑反射 ──
    "tower_exterior": {
        "base": "bg_tower_exterior.png",
        "ambient": 0.02,
        "lights": [
            # 大厅暖光（从建筑内部透出）
            {"name": "lobby", "pos": (480, 450),
             "color": [1.0, 0.9, 0.7], "intensity": (0.06, 0.2),
             "radius": 400, "phase": _pulse_slow},
            # 玻璃幕墙反射（冷色）
            {"name": "glass", "pos": (480, 200),
             "color": [0.4, 0.5, 0.7], "intensity": (0.03, 0.1),
             "radius": 500, "phase": _moonlight_clouds},
            # 岗亭灯
            {"name": "booth", "pos": (250, 520),
             "color": [0.9, 0.85, 0.6], "intensity": (0.04, 0.12),
             "radius": 200, "phase": _steady},
        ],
    },

    # ── 服务器机房：LED 闪烁 + 荧光灯 + 终端 ──
    "server_room": {
        "base": "bg_server_room.png",
        "ambient": 0.03,
        "lights": [
            # 蓝色 LED（机架）
            {"name": "led_blue", "pos": (200, 300),
             "color": [0.1, 0.3, 0.9], "intensity": (0.04, 0.2),
             "radius": 350, "phase": _irregular_screen},
            # 绿色 LED（机架）
            {"name": "led_green", "pos": (700, 280),
             "color": [0.1, 0.8, 0.2], "intensity": (0.03, 0.15),
             "radius": 300, "phase": _phase_shift(_irregular_screen, 3)},
            # 荧光灯（顶部，偶尔闪烁）
            {"name": "fluorescent", "pos": (480, 50),
             "color": [0.9, 0.95, 1.0], "intensity": (0.06, 0.18),
             "radius": 600, "phase": _flicker},
            # 终端屏幕
            {"name": "terminal", "pos": (480, 400),
             "color": [0.2, 0.7, 0.3], "intensity": (0.03, 0.12),
             "radius": 250, "phase": _phase_shift(_irregular_screen, 7)},
        ],
    },

    # ── 天台：城市霓虹光 + 闪电 + 天线灯 ──
    "rooftop": {
        "base": "bg_rooftop.png",
        "ambient": 0.015,
        "lights": [
            # 城市霓虹辉光（远处，冷色）
            {"name": "city_glow", "pos": (480, 400),
             "color": [0.3, 0.4, 0.7], "intensity": (0.04, 0.15),
             "radius": 600, "phase": _moonlight_clouds},
            # 闪电
            {"name": "lightning", "pos": (600, 80),
             "color": [0.9, 0.92, 1.0], "intensity": (0.0, 0.4),
             "radius": 800, "phase": _lightning},
            # 天线红灯
            {"name": "antenna", "pos": (750, 120),
             "color": [0.9, 0.1, 0.05], "intensity": (0.03, 0.1),
             "radius": 200, "phase": _pulse_medium},
        ],
    },

    # ── 办公室：全息屏 + 台灯 + 窗外城市 ──
    "office": {
        "base": "bg_office.png",
        "ambient": 0.02,
        "lights": [
            # 全息显示屏（蓝色）
            {"name": "hologram", "pos": (480, 300),
             "color": [0.15, 0.4, 0.9], "intensity": (0.05, 0.22),
             "radius": 350, "phase": _irregular_screen},
            # 台灯（暖琥珀）
            {"name": "desk_lamp", "pos": (650, 380),
             "color": [1.0, 0.8, 0.5], "intensity": (0.04, 0.15),
             "radius": 280, "phase": _pulse_slow},
            # 窗外城市光
            {"name": "window", "pos": (100, 250),
             "color": [0.4, 0.5, 0.7], "intensity": (0.03, 0.1),
             "radius": 400, "phase": _moonlight_clouds},
        ],
    },
}


# ── Depth Model ───────────────────────────────────────────────────

def load_depth_model():
    """Load Depth-Anything-V2-Large via transformers pipeline."""
    from transformers import pipeline
    print(f"  Loading model from {HF_ENDPOINT}...")
    t0 = time.time()
    pipe = pipeline("depth-estimation", model=HF_MODEL, device="cpu",
                    torch_dtype=torch.float32)
    print(f"  ✓ Model loaded ({time.time()-t0:.1f}s)")
    return pipe


def generate_depth_map(pipe, base_image):
    """Generate depth map using transformers pipeline."""
    from PIL import Image
    pil_img = Image.fromarray(base_image)
    t0 = time.time()
    result = pipe(pil_img)
    print(f"  ✓ Inference done ({time.time()-t0:.1f}s)")
    depth = np.array(result["depth"])
    return depth.astype(np.float32)


def postprocess_depth(depth, target_h, target_w):
    """Normalize, resize, and smooth depth map."""
    if depth.shape[:2] != (target_h, target_w):
        depth = cv2.resize(depth, (target_w, target_h),
                           interpolation=cv2.INTER_LINEAR)
    depth_norm = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
    depth_u8 = (depth_norm * 255).astype(np.uint8)
    return cv2.bilateralFilter(depth_u8, 9, 75, 75)


# ── Lighting Engine ───────────────────────────────────────────────

def compute_lighting(depth_map, frame_idx, img_h, img_w, scene_config):
    """Compute per-pixel lighting for a single frame."""
    depth_float = depth_map.astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    total_light = np.zeros((img_h, img_w, 3), dtype=np.float32)
    total_light += scene_config.get("ambient", AMBIENT)

    for src in scene_config["lights"]:
        lx, ly = src["pos"]
        color = np.array(src["color"])
        r_min, r_max = src["intensity"]
        radius = src["radius"]

        intensity = r_min + (r_max - r_min) * src["phase"](frame_idx, NUM_FRAMES)

        dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2)
        attenuation = 1.0 / (1.0 + (dist / radius) ** 2)
        depth_factor = 1.0 - depth_float
        shadow = ray_march_shadows(depth_float, (lx, ly), img_h, img_w)

        contrib = (color[np.newaxis, np.newaxis, :] *
                   intensity *
                   attenuation[:, :, np.newaxis] *
                   depth_factor[:, :, np.newaxis] *
                   shadow[:, :, np.newaxis])
        total_light += contrib

    return np.clip(total_light, 0.0, 1.5)


def ray_march_shadows(depth_map, light_pos, img_h, img_w):
    """March shadow rays from each pixel toward the light source."""
    lx, ly = light_pos
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    dx = lx - xx
    dy = ly - yy
    dist = np.sqrt(dx * dx + dy * dy)

    eps = 1e-8
    dx_norm = dx / (dist + eps)
    dy_norm = dy / (dist + eps)

    step_dist = dist / SHADOW_STEPS
    shadow = np.ones((img_h, img_w), dtype=np.float32)
    current_depth = depth_map

    for step in range(1, SHADOW_STEPS + 1):
        sx = np.clip(xx + dx_norm * step_dist * step, 0, img_w - 1).astype(np.int32)
        sy = np.clip(yy + dy_norm * step_dist * step, 0, img_h - 1).astype(np.int32)
        sampled_depth = depth_map[sy, sx]
        shadow_mask = (sampled_depth > current_depth + 0.05).astype(np.float32)
        shadow *= (1.0 - shadow_mask)

    return shadow


def composite_frame(base_image, lighting):
    """Additive blending."""
    base_float = base_image.astype(np.float32) / 255.0
    result = base_float + lighting
    return np.clip(result * 255, 0, 255).astype(np.uint8)


def quality_report(scene_name, frames):
    """Print quality metrics."""
    print(f"\n── {scene_name} Quality Report ──")
    diffs = []
    for i in range(1, len(frames)):
        d = np.mean(cv2.absdiff(frames[i - 1], frames[i]))
        diffs.append(d)
    avg = np.mean(diffs)
    loop = np.mean(cv2.absdiff(frames[0], frames[-1]))
    print(f"  Avg inter-frame diff: {avg:.2f}  |  Loop closure: {loop:.2f}")
    status = "✓" if avg < 20 else "⚠️"
    print(f"  {status} Frames look {'good' if avg < 20 else 'high variation'}")


# ── Main ──────────────────────────────────────────────────────────

def render_scene(scene_name, scene_config, pipe=None, lighting_only=False):
    """Render one scene's animation frames."""
    base_file = scene_config["base"]
    base_path = os.path.join(ASSETS_DIR, base_file)
    depth_path = os.path.join(ASSETS_DIR, f"{scene_name}_depth.png")

    print(f"\n{'='*50}")
    print(f"🎬 {scene_name}")
    print(f"{'='*50}")

    # Load base image
    base_image = cv2.imread(base_path)
    if base_image is None:
        print(f"  ✗ Cannot load {base_path}")
        return False
    base_rgb = cv2.cvtColor(base_image, cv2.COLOR_BGR2RGB)
    img_h, img_w = base_rgb.shape[:2]
    print(f"  ✓ Base: {img_w}×{img_h}")

    # Depth map: skip if exists
    if lighting_only:
        depth_map = cv2.imread(depth_path, cv2.IMREAD_GRAYSCALE)
        if depth_map is None:
            print(f"  ✗ No cached depth at {depth_path}, run without --lighting-only")
            return False
        print(f"  ✓ Depth cache: {depth_path}")
    elif os.path.exists(depth_path):
        depth_map = cv2.imread(depth_path, cv2.IMREAD_GRAYSCALE)
        print(f"  ✓ Depth cache exists, skipping generation: {depth_path}")
    else:
        if pipe is None:
            pipe = load_depth_model()
        raw_depth = generate_depth_map(pipe, base_rgb)
        depth_map = postprocess_depth(raw_depth, img_h, img_w)
        cv2.imwrite(depth_path, depth_map)
        print(f"  ✓ Depth saved: {depth_path}")

    # Render frames
    print(f"  Rendering {NUM_FRAMES} frames...")
    frames = []
    for i in range(NUM_FRAMES):
        t0 = time.time()
        lighting = compute_lighting(depth_map, i, img_h, img_w, scene_config)
        frame = composite_frame(base_rgb, lighting)
        out_path = os.path.join(ASSETS_DIR, f"bg_{scene_name}_f{i}.png")
        cv2.imwrite(out_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        frames.append(frame)
        print(f"    f{i} ({time.time()-t0:.1f}s)")

    quality_report(scene_name, frames)
    return True


def main():
    parser = argparse.ArgumentParser(description="Depth lighting renderer for all scenes")
    parser.add_argument("--scene", type=str, help="Render single scene only")
    parser.add_argument("--lighting-only", action="store_true", help="Skip depth, reuse cache")
    parser.add_argument("--depth-only", action="store_true", help="Generate depth maps only")
    args = parser.parse_args()

    start_all = time.time()

    scenes = {args.scene: SCENE_LIGHTS[args.scene]} if args.scene else SCENE_LIGHTS
    pipe = None

    for name, config in scenes.items():
        if args.depth_only:
            # Only generate depth
            base_path = os.path.join(ASSETS_DIR, config["base"])
            depth_path = os.path.join(ASSETS_DIR, f"{name}_depth.png")
            if os.path.exists(depth_path):
                print(f"✓ {name}: depth cache exists, skipping")
                continue
            base_image = cv2.imread(base_path)
            if base_image is None:
                print(f"✗ {name}: cannot load {base_path}")
                continue
            base_rgb = cv2.cvtColor(base_image, cv2.COLOR_BGR2RGB)
            if pipe is None:
                pipe = load_depth_model()
            raw_depth = generate_depth_map(pipe, base_rgb)
            depth_map = postprocess_depth(raw_depth, *base_rgb.shape[:2])
            cv2.imwrite(depth_path, depth_map)
            print(f"✓ {name}: depth saved")
        else:
            ok = render_scene(name, config, pipe=pipe, lighting_only=args.lighting_only)
            if ok and pipe is None and not args.lighting_only and not os.path.exists(
                    os.path.join(ASSETS_DIR, f"{name}_depth.png")):
                # pipe was loaded inside render_scene, keep it for next scenes
                pass

    total = time.time() - start_all
    print(f"\n✓ All done in {total:.1f}s")


if __name__ == "__main__":
    main()
