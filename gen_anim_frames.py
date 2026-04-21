#!/usr/bin/env python3
"""
LAST SIGNAL - 动画帧生成器
从一张基础场景图扩展出 5 帧动画，使用程序化图像效果：
  f0: 原图
  f1: 霓虹脉冲（亮度微调）
  f2: 雨滴增强
  f3: 光源闪烁（局部亮度变化）
  f4: 薄雾弥漫
效果足够微妙，形成缓慢呼吸的环境动画。
"""

import cv2
import numpy as np
import os

ASSETS_DIR = "/root/.openclaw/workspace/last-signal/assets"

SCENES = [
    "bg_apartment", "bg_street", "bg_bar", "bg_alley",
    "bg_tower_exterior", "bg_server_room", "bg_rooftop", "bg_office",
]


def frame_neon_pulse(img):
    """f1: 霓虹脉冲 — 提亮高饱和度区域（霓虹灯区域）"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    # 高饱和度区域 = 霓虹灯
    sat_mask = hsv[:, :, 1] > 80
    out = img.astype(np.float32).copy()
    # 霓虹区域亮度 +15%
    out[sat_mask] = np.clip(out[sat_mask] * 1.15, 0, 255)
    # 整体微亮
    out = np.clip(out * 1.03, 0, 255)
    return out.astype(np.uint8)


def frame_rain_enhance(img):
    """f2: 雨滴增强 — 添加雨丝纹理 + 湿润反光"""
    h, w = img.shape[:2]
    out = img.astype(np.float32).copy()

    # 生成随机雨丝
    rain = np.zeros((h, w), np.uint8)
    num_drops = 300
    xs = np.random.randint(0, w, num_drops)
    ys = np.random.randint(0, h, num_drops)
    lengths = np.random.randint(8, 25, num_drops)
    for x, y, l in zip(xs, ys, lengths):
        x2 = x + np.random.randint(-2, 3)
        y2 = min(y + l, h - 1)
        cv2.line(rain, (x, y), (x2, y2), 180, 1)

    # 雨丝叠加到图像（偏蓝色调）
    rain_3ch = np.stack([rain * 0.7, rain * 0.8, rain], axis=-1)
    out = np.clip(out + rain_3ch * 0.25, 0, 255)

    # 底部湿润反光（轻微提亮）
    bottom = int(h * 0.7)
    out[bottom:h, :, :] = np.clip(out[bottom:h, :, :] * 1.06, 0, 255)

    return out.astype(np.uint8)


def frame_light_flicker(img):
    """f3: 光源闪烁 — 降低整体亮度 + 局部随机暗区"""
    out = img.astype(np.float32).copy()

    # 整体微暗
    out = np.clip(out * 0.92, 0, 255)

    # 添加 2-3 个随机暗区（模拟灯光闪烁）
    h, w = img.shape[:2]
    for _ in range(3):
        cx = np.random.randint(w // 4, 3 * w // 4)
        cy = np.random.randint(h // 4, 3 * h // 4)
        radius = np.random.randint(80, 200)
        Y, X = np.ogrid[:h, :w]
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        mask = dist < radius
        fade = np.clip(1.0 - (dist / radius) * 0.2, 0.75, 1.0)
        for c in range(3):
            out[:, :, c] = out[:, :, c] * fade

    return np.clip(out, 0, 255).astype(np.uint8)


def frame_fog(img):
    """f4: 薄雾弥漫 — 从上方渐变加雾"""
    h, w = img.shape[:2]
    out = img.astype(np.float32).copy()

    # 创建从上到下的雾渐变（上方更浓，下方几乎无）
    fog_alpha = np.linspace(0.18, 0.0, h).reshape(h, 1)       # (h, 1)
    fog_alpha = np.broadcast_to(fog_alpha, (h, w)).copy()      # (h, w)

    # 雾的颜色（偏蓝灰）
    fog_r, fog_g, fog_b = 140, 138, 155

    # 逐通道混合: out = out * (1-a) + fog * a
    out[:, :, 0] = out[:, :, 0] * (1 - fog_alpha) + fog_b * fog_alpha
    out[:, :, 1] = out[:, :, 1] * (1 - fog_alpha) + fog_g * fog_alpha
    out[:, :, 2] = out[:, :, 2] * (1 - fog_alpha) + fog_r * fog_alpha

    return np.clip(out, 0, 255).astype(np.uint8)


FRAME_EFFECTS = [
    ("f0", None),                 # 原图
    ("f1", frame_neon_pulse),      # 霓虹脉冲
    ("f2", frame_rain_enhance),    # 雨滴增强
    ("f3", frame_light_flicker),   # 光源闪烁
    ("f4", frame_fog),             # 薄雾弥漫
]


def generate_frames(scene_name):
    """为一个场景生成 5 帧动画"""
    src = os.path.join(ASSETS_DIR, f"{scene_name}.png")
    if not os.path.exists(src):
        print(f"  ❌ 缺少基础图: {src}")
        return 0

    img = cv2.imread(src)
    if img is None:
        print(f"  ❌ 无法读取: {src}")
        return 0

    ok = 0
    for fname, effect_fn in FRAME_EFFECTS:
        out_path = os.path.join(ASSETS_DIR, f"{scene_name}_{fname}.png")

        # 跳过已有文件
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            print(f"  ⏭️  {fname} 已有")
            ok += 1
            continue

        if effect_fn is None:
            # f0 = 原图（复制）
            frame = img.copy()
        else:
            frame = effect_fn(img)

        cv2.imwrite(out_path, frame)
        size_kb = os.path.getsize(out_path) // 1024
        print(f"  ✅ {fname} ({size_kb}KB)")
        ok += 1

    return ok


def main():
    print("=" * 50)
    print("🎬 LAST SIGNAL - 动画帧生成")
    print("   基于程序化图像效果，从基础图扩展 5 帧")
    print("=" * 50)

    total_ok = 0
    total_fail = 0

    for scene in SCENES:
        print(f"\n📁 {scene}:")
        got = generate_frames(scene)
        total_ok += got
        total_fail += (5 - got)

    print(f"\n{'='*50}")
    print(f"✅ 成功: {total_ok}  ❌ 跳过/失败: {total_fail}")
    print(f"📁 {ASSETS_DIR}")


if __name__ == "__main__":
    main()
