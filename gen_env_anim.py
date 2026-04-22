#!/usr/bin/env python3
"""
LAST SIGNAL - 定向环境动画 v3 (apartment)

核心思路：效果要极端、局部要大、变化要快。
- 终端屏幕：像真的 CRT 在闪烁，亮度变化 > 100%
- 天花板灯：真的灭/亮，不是微调
- 窗户雨：肉眼可见的雨丝变化
- 每帧都有至少一个显著变化点
"""

import cv2
import numpy as np
import os

ASSETS_DIR = "/root/.openclaw/workspace/last-signal/assets"
SCENE = "bg_apartment"

# 区域 (扩大范围以覆盖更多像素)
TERMINAL = (420, 300, 940, 620)   # 终端+桌面
CEILING  = (100, 0, 700, 200)     # 天花板灯区域
WINDOW   = (0, 60, 470, 580)      # 窗户区域


def load_base():
    path = os.path.join(ASSETS_DIR, f"{SCENE}_f0.png")
    return cv2.imread(path)


def mask_blend(base, transformed, region, feather=30):
    """用羽化 mask 混合区域效果"""
    h, w = base.shape[:2]
    x1, y1, x2, y2 = [max(0, region[0]), max(0, region[1]),
                        min(w, region[2]), min(h, region[3])]

    mask = np.zeros((h, w), np.float32)
    mask[y1:y2, x1:x2] = 1.0
    ks = feather * 2 + 1
    mask = cv2.GaussianBlur(mask, (ks, ks), feather)
    if mask.max() > 0:
        mask /= mask.max()
    m3 = np.stack([mask]*3, axis=-1)

    bf = base.astype(np.float32)
    tf = transformed.astype(np.float32)
    return np.clip(bf * (1 - m3) + tf * m3, 0, 255).astype(np.uint8)


# ========== 效果 ==========

def fx_terminal_green_flash(img):
    """终端区域强绿色脉冲 — 像 CRT 闪亮"""
    out = img.copy().astype(np.float32)
    x1, y1, x2, y2 = TERMINAL
    r = out[y1:y2, x1:x2]
    # 绿色通道大幅提亮
    r[:, :, 1] = np.clip(r[:, :, 1] * 2.2 + 40, 0, 255)
    # 红蓝压制
    r[:, :, 0] = np.clip(r[:, :, 0] * 0.5, 0, 255)
    r[:, :, 2] = np.clip(r[:, :, 2] * 0.55, 0, 255)
    # 整体提亮
    r[:] = np.clip(r * 1.5, 0, 255)
    return out.astype(np.uint8)


def fx_terminal_off(img):
    """终端区域暗灭 — 几乎全黑"""
    out = img.copy().astype(np.float32)
    x1, y1, x2, y2 = TERMINAL
    out[y1:y2, x1:x2] *= 0.25
    return np.clip(out, 0, 255).astype(np.uint8)


def fx_terminal_flicker(img):
    """终端闪烁 — 亮度波动 + 色温偏移"""
    out = img.copy().astype(np.float32)
    x1, y1, x2, y2 = TERMINAL
    r = out[y1:y2, x1:x2]
    r[:, :, 1] = np.clip(r[:, :, 1] * 1.6 + 25, 0, 255)
    r[:, :, 0] = np.clip(r[:, :, 0] * 0.7, 0, 255)
    r[:, :, 2] = np.clip(r[:, :, 2] * 0.75, 0, 255)
    r[:] = np.clip(r * 1.35, 0, 255)
    return out.astype(np.uint8)


def fx_ceiling_warm(img):
    """天花板灯偏暖亮"""
    out = img.copy().astype(np.float32)
    x1, y1, x2, y2 = CEILING
    r = out[y1:y2, x1:x2]
    r[:, :, 2] = np.clip(r[:, :, 2] * 1.4 + 20, 0, 255)
    r[:, :, 1] = np.clip(r[:, :, 1] * 1.2, 0, 255)
    r[:, :, 0] = np.clip(r[:, :, 0] * 0.6, 0, 255)
    r[:] = np.clip(r * 1.4, 0, 255)
    return out.astype(np.uint8)


def fx_ceiling_dark(img):
    """天花板灯灭 — 大幅压暗"""
    out = img.copy().astype(np.float32)
    x1, y1, x2, y2 = CEILING
    out[y1:y2, x1:x2] *= 0.2
    return np.clip(out, 0, 255).astype(np.uint8)


def fx_window_rain(img):
    """窗户区域密集雨丝"""
    out = img.copy().astype(np.float32)
    h, w = out.shape[:2]
    x1, y1, x2, y2 = WINDOW
    rain = np.zeros((h, w), np.float32)
    n = 300
    xs = np.random.randint(x1, x2, n)
    ys = np.random.randint(y1, y2, n)
    ls = np.random.randint(10, 35, n)
    for x, y, l in zip(xs, ys, ls):
        x2r = x + np.random.randint(-2, 3)
        y2r = min(y + l, y2)
        cv2.line(rain, (x, y), (x2r, y2r), 1.0, 1)
    out[:, :, 0] = np.clip(out[:, :, 0] + rain * 80, 0, 255)
    out[:, :, 1] = np.clip(out[:, :, 1] + rain * 65, 0, 255)
    out[:, :, 2] = np.clip(out[:, :, 2] + rain * 50, 0, 255)
    # 窗户微亮
    out[y1:y2, x1:x2] = np.clip(out[y1:y2, x1:x2] * 1.15, 0, 255)
    return out.astype(np.uint8)


def fx_window_light_rain(img):
    """窗户区域轻雨"""
    out = img.copy().astype(np.float32)
    h, w = out.shape[:2]
    x1, y1, x2, y2 = WINDOW
    rain = np.zeros((h, w), np.float32)
    n = 100
    xs = np.random.randint(x1, x2, n)
    ys = np.random.randint(y1, y2, n)
    ls = np.random.randint(5, 18, n)
    for x, y, l in zip(xs, ys, ls):
        x2r = x + np.random.randint(-1, 2)
        y2r = min(y + l, y2)
        cv2.line(rain, (x, y), (x2r, y2r), 0.7, 1)
    out[:, :, 0] = np.clip(out[:, :, 0] + rain * 50, 0, 255)
    out[:, :, 1] = np.clip(out[:, :, 1] + rain * 40, 0, 255)
    out[:, :, 2] = np.clip(out[:, :, 2] + rain * 30, 0, 255)
    return out.astype(np.uint8)


def fx_global_cold(img):
    """全局偏冷"""
    out = img.copy().astype(np.float32)
    out[:, :, 0] = np.clip(out[:, :, 0] * 1.1 + 5, 0, 255)
    out[:, :, 2] = np.clip(out[:, :, 2] * 0.9, 0, 255)
    return out.astype(np.uint8)


# ============================================================
# 帧定义：每帧组合多个区域效果
# ============================================================

def gen():
    base = load_base()
    frames = []

    # f0: 基准
    frames.append(base.copy())

    # f1: 终端绿闪 + 天花板暖亮
    f1 = mask_blend(base, fx_terminal_green_flash(base), TERMINAL)
    f1 = mask_blend(f1, fx_ceiling_warm(f1), CEILING)
    frames.append(f1)

    # f2: 终端灭 + 窗户雨
    f2 = mask_blend(base, fx_terminal_off(base), TERMINAL)
    f2 = fx_window_rain(f2)
    frames.append(f2)

    # f3: 终端闪 + 天花板暗
    f3 = mask_blend(base, fx_terminal_flicker(base), TERMINAL)
    f3 = mask_blend(f3, fx_ceiling_dark(f3), CEILING)
    frames.append(f3)

    # f4: 全局冷 + 终端绿闪（峰值帧）
    f4 = fx_global_cold(base.copy())
    f4 = mask_blend(f4, fx_terminal_green_flash(f4), TERMINAL)
    frames.append(f4)

    # f5: 终端灭 + 天花板暖 + 窗户轻雨
    f5 = mask_blend(base, fx_terminal_off(base), TERMINAL)
    f5 = mask_blend(f5, fx_ceiling_warm(f5), CEILING)
    f5 = fx_window_light_rain(f5)
    frames.append(f5)

    # f6: 终端闪 + 窗户雨
    f6 = mask_blend(base, fx_terminal_flicker(base), TERMINAL)
    f6 = fx_window_rain(f6)
    frames.append(f6)

    # f7: 终端微闪（过渡回基准）
    f7 = mask_blend(base, fx_terminal_flicker(base), TERMINAL)
    frames.append(f7)

    return frames


def main():
    print("=" * 50)
    print("🎬 LAST SIGNAL - 定向环境动画 v3 (apartment)")
    print("=" * 50)

    np.random.seed(42)  # 固定雨丝位置便于对比
    frames = gen()

    for i, f in enumerate(frames):
        out = os.path.join(ASSETS_DIR, f"{SCENE}_f{i}.png")
        cv2.imwrite(out, f)
        sz = os.path.getsize(out) // 1024
        print(f"  ✅ f{i} ({sz}KB)")

    print(f"\n📊 帧间差异:")
    for i in range(1, len(frames)):
        diff = np.mean(cv2.absdiff(frames[0], frames[i]))
        bar = "█" * int(diff) + "░" * max(0, 30 - int(diff))
        label = "太微" if diff < 3 else "微妙" if diff < 8 else "可见" if diff < 18 else "明显"
        print(f"   f0↔f{i}: {diff:5.1f} {bar} [{label}]")

    loop = np.mean(cv2.absdiff(frames[0], frames[-1]))
    print(f"   循环: f0↔f{len(frames)-1}: {loop:.1f}")


if __name__ == "__main__":
    main()
