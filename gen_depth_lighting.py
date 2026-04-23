#!/usr/bin/env python3
"""
gen_depth_lighting.py — Depth-based lighting renderer for ALL scenes

Unified depth-based lighting renderer for all scenes. Uses Depth-Anything-V2-Large for depth
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

# ── Constants ──────────────────────────────────────────────────────
ASSETS_DIR = "assets"
NUM_FRAMES = 24
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
    """车灯：不规则扫过 + soft threshold，明暗对比强烈。"""
    t = 2 * math.pi * frame_idx / num_frames
    v = (0.5 + 0.5 * math.sin(t * 1.0 + 0.0)
         + 0.3 * math.sin(t * 3.0 + 1.2)
         + 0.2 * math.sin(t * 5.0 + 2.8))
    v = v / 1.0
    v = max(0.0, min(1.0, v))
    # 提高对比度：暗区更暗，亮区更亮
    if v < 0.4:
        v *= 0.1   # 没车时几乎全暗
    elif v < 0.6:
        alpha = (v - 0.4) / 0.2
        alpha = alpha * alpha * (3 - 2 * alpha)  # smoothstep
        v = 0.4 * 0.1 * (1 - alpha) + v * alpha
    else:
        v = 0.6 + (v - 0.6) * 1.5  # 拉高亮区
    return max(0.0, min(1.0, v))


def _car_sweep(frame_idx, num_frames):
    """车灯 mask 平移相位：从左到右匀速扫过窗户区域。
    返回 0~1，0=车在最左（光刚进窗），1=车在最右（光已离开窗）。
    """
    t = frame_idx / num_frames
    # 用两个半周期：0→1→0，形成往返效果
    if t < 0.5:
        return t * 2.0
    else:
        return 2.0 - t * 2.0


def _make_car_dir_phase(car_x_range, window_center):
    """生成车灯光源方向相位函数。
    car_x_range: (x_start, x_end) 车的水平移动范围
    window_center: (wx, wy) 窗户中心坐标
    返回 lambda frame_idx, num_frames → (dx, dy) 归一化方向向量
    同时附加 .visibility 属性用于强度调制
    """
    wx, wy = window_center
    def _dir_phase(frame_idx, num_frames):
        t = _car_sweep(frame_idx, num_frames)
        x0, x1 = car_x_range
        car_x = x0 + (x1 - x0) * t
        car_y = 580  # 车在画面底部（街道高度）
        dx = wx - car_x
        dy = wy - car_y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            return (1.0, 0.0)
        return (dx / length, dy / length)
    return _dir_phase


def _make_car_visibility(car_x_range, window_x_range=(-100, 600)):
    """生成车灯可见性相位：车在窗户可视角度内时返回 1，否则平滑淡出。
    window_x_range: 车的 x 坐标在此范围内时灯光能照到窗户
    """
    wx1, wx2 = window_x_range
    fade = 80.0  # 淡出像素宽度
    def _vis(frame_idx, num_frames):
        t = _car_sweep(frame_idx, num_frames)
        x0, x1 = car_x_range
        car_x = x0 + (x1 - x0) * t
        if car_x < wx1:
            return max(0.0, (car_x - (wx1 - fade)) / fade)
        elif car_x > wx2:
            return max(0.0, ((wx2 + fade) - car_x) / fade)
        return 1.0
    return _vis

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
            # 月光：方向光，从窗户射入，物理光锥扩散
            {"name": "moonlight",
             "distant": True,
             "dir": (1, 0.3),
             "color": [0.55, 0.65, 0.85], "intensity": (0.15, 0.45),
             "phase": _moonlight_clouds,
             "mask": {"type": "frustum", "mask_file": "assets/masks/apartment_window_mask.png",
                      "spread": 0.5, "direction": "right", "feather": 30, "max_depth": 500,
                      "glass_feather": 12}},
            # 车灯：方向光（平行光），从窗户射入，物理光锥扩散
            # 光从窗户（光圈）进入后呈梯形扩散，不穿墙
            {"name": "car1",
             "distant": True,
             "dir": (1, 0.4),
             "color": [1.0, 0.92, 0.7], "intensity": (0.0, 0.035),
             "phase": _irregular_car,
             "mask": {"type": "frustum", "mask_file": "assets/masks/apartment_window_mask.png",
                      "spread": 0.03, "direction": "right", "feather": 20, "max_depth": 500,
                      "glass_feather": 10, "dir_key": "auto"},
             "dir_phase": _make_car_dir_phase((-200, 600), (231, 298)),
             "vis_phase": _make_car_visibility((-200, 600), (-50, 450))},
            {"name": "car2",
             "distant": True,
             "dir": (1, 0.35),
             "color": [1.0, 0.85, 0.6], "intensity": (0.0, 0.025),
             "phase": _phase_shift(_irregular_car, 3),
             "mask": {"type": "frustum", "mask_file": "assets/masks/apartment_window_mask.png",
                      "spread": 0.03, "direction": "right", "feather": 20, "max_depth": 500,
                      "glass_feather": 10, "dir_key": "auto"},
             "dir_phase": _make_car_dir_phase((-300, 500), (231, 298)),
             "vis_phase": _make_car_visibility((-300, 500), (-100, 350))},
            # 屏幕光：照亮桌面和面对屏幕的墙壁
            {"name": "screen", "pos": (770, 320),
             "color": [0.15, 0.7, 0.25], "intensity": (0.06, 0.35),
             "radius": 280, "phase": _irregular_screen,
             "mask": {"type": "cone", "dir": (-0.5, 1), "angle_deg": 100, "feather": 25}},
            {"name": "screen_flash", "pos": (750, 280),
             "color": [0.3, 0.85, 0.4], "intensity": (0.0, 0.15),
             "radius": 200, "phase": _phase_shift(_irregular_screen, 5),
             "mask": {"type": "cone", "dir": (-0.3, 1), "angle_deg": 80, "feather": 20}},
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
             "color": [1.0, 0.95, 0.8], "intensity": (0.0, 0.06),
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

    # ── ECHO 大厅：冷白灯光 + 全息投影 + 安检扫描 ──
    "echo_lobby": {
        "base": "bg_echo_lobby.png",
        "ambient": 0.03,
        "lights": [
            # 大厅顶灯（冷白）
            {"name": "ceiling", "pos": (480, 80),
             "color": [0.85, 0.9, 1.0], "intensity": (0.06, 0.2),
             "radius": 600, "phase": _steady},
            # 全息公司标志（蓝色脉冲）
            {"name": "holo_logo", "pos": (480, 250),
             "color": [0.1, 0.4, 0.9], "intensity": (0.04, 0.18),
             "radius": 300, "phase": _pulse_slow},
            # 安检门扫描（红色闪烁）
            {"name": "scanner", "pos": (480, 450),
             "color": [0.9, 0.15, 0.1], "intensity": (0.02, 0.1),
             "radius": 250, "phase": _flicker},
            # 电梯指示灯（琥珀色）
            {"name": "elevator", "pos": (820, 350),
             "color": [1.0, 0.7, 0.2], "intensity": (0.03, 0.1),
             "radius": 200, "phase": _pulse_medium},
        ],
    },

    # ── 地下维护通道：红色应急灯 + 蒸汽 + 管道 ──
    "maintenance": {
        "base": "bg_maintenance.png",
        "ambient": 0.015,
        "lights": [
            # 红色应急灯（左侧）
            {"name": "emergency_l", "pos": (150, 100),
             "color": [0.9, 0.1, 0.05], "intensity": (0.04, 0.15),
             "radius": 350, "phase": _pulse_medium},
            # 红色应急灯（右侧）
            {"name": "emergency_r", "pos": (800, 120),
             "color": [0.85, 0.08, 0.05], "intensity": (0.03, 0.12),
             "radius": 300, "phase": _phase_shift(_pulse_medium, 4)},
            # 管道接缝漏光（暖黄）
            {"name": "pipe_leak", "pos": (400, 350),
             "color": [0.9, 0.8, 0.5], "intensity": (0.02, 0.08),
             "radius": 200, "phase": _steady},
            # 远处防爆门缝隙（冷蓝）
            {"name": "blast_door", "pos": (480, 400),
             "color": [0.3, 0.4, 0.7], "intensity": (0.02, 0.06),
             "radius": 300, "phase": _steady},
        ],
    },

    # ── 数据避难所：多屏幕 + 霓虹 + 车站灯 ──
    "data_haven": {
        "base": "bg_data_haven.png",
        "ambient": 0.02,
        "lights": [
            # 主屏幕组（青色）
            {"name": "screen_cyan", "pos": (300, 280),
             "color": [0.1, 0.8, 0.9], "intensity": (0.05, 0.22),
             "radius": 350, "phase": _irregular_screen},
            # 副屏幕（绿色）
            {"name": "screen_green", "pos": (650, 300),
             "color": [0.15, 0.7, 0.2], "intensity": (0.04, 0.18),
             "radius": 300, "phase": _phase_shift(_irregular_screen, 3)},
            # 霓虹装饰（品红）
            {"name": "neon_pink", "pos": (480, 100),
             "color": [0.9, 0.15, 0.5], "intensity": (0.03, 0.12),
             "radius": 400, "phase": _flicker},
            # 旧列车内部灯（暖色）
            {"name": "train_light", "pos": (850, 450),
             "color": [1.0, 0.85, 0.6], "intensity": (0.02, 0.08),
             "radius": 250, "phase": _steady},
        ],
    },

    # ── 闪回实验室：冷白临床灯 + 警报 + 舱体光 ──
    "flashback": {
        "base": "bg_flashback.png",
        "ambient": 0.05,
        "lights": [
            # 临床顶灯（冷白，高压）
            {"name": "clinical", "pos": (480, 60),
             "color": [0.9, 0.95, 1.0], "intensity": (0.08, 0.3),
             "radius": 600, "phase": _steady},
            # 警报灯（红色脉冲，渐强）
            {"name": "alarm", "pos": (480, 300),
             "color": [0.9, 0.1, 0.05], "intensity": (0.02, 0.25),
             "radius": 500, "phase": _pulse_medium},
            # 3号舱体（异常闪烁）
            {"name": "pod_3", "pos": (350, 350),
             "color": [0.3, 0.6, 0.9], "intensity": (0.04, 0.2),
             "radius": 250, "phase": _flicker},
            # 全息监控屏（蓝色）
            {"name": "monitor", "pos": (650, 250),
             "color": [0.15, 0.4, 0.85], "intensity": (0.03, 0.12),
             "radius": 200, "phase": _irregular_screen},
        ],
    },

    # ── 医院走廊：自然阳光 + 走廊灯 + 窗光 ──
    "hospital": {
        "base": "bg_hospital.png",
        "ambient": 0.04,
        "lights": [
            # 窗户阳光（暖色，主光源）
            {"name": "sunlight", "pos": (800, 300),
             "color": [1.0, 0.95, 0.8], "intensity": (0.08, 0.3),
             "radius": 500, "phase": _steady},
            # 走廊灯（冷白）
            {"name": "corridor", "pos": (480, 50),
             "color": [0.85, 0.9, 0.95], "intensity": (0.04, 0.12),
             "radius": 400, "phase": _steady},
            # 病房门缝光（暖黄）
            {"name": "room_light", "pos": (200, 400),
             "color": [1.0, 0.9, 0.7], "intensity": (0.02, 0.08),
             "radius": 200, "phase": _pulse_slow},
        ],
    },
}


# ── Light Mask System ─────────────────────────────────────────────
# 每个光源可以有一个 mask，限制光的影响区域。
# mask 定义格式：
#   {"type": "rect",    "region": (x1,y1,x2,y2), "feather": px}  — 矩形区域内生效
#   {"type": "outside", "region": (x1,y1,x2,y2), "feather": px}  — 矩形区域外生效（阻挡光进入该区域）
#   {"type": "cone",    "dir": (dx,dy), "angle_deg": N, "feather": deg}  — 锥形方向光
# feather = 边缘渐变宽度（像素或度数）

def generate_light_mask(mask_def, img_h, img_w, light_pos):
    """根据 mask 定义生成 (H,W) 的软遮罩，值 0~1。"""
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    if mask_def["type"] == "rect":
        x1, y1, x2, y2 = mask_def["region"]
        feather = mask_def.get("feather", 40)
        # 硬边界
        inside = np.ones((img_h, img_w), dtype=np.float32)
        # X 方向渐变
        if x1 > 0:
            inside *= np.clip((xx - x1) / feather, 0, 1)
        if x2 < img_w:
            inside *= np.clip((x2 - xx) / feather, 0, 1)
        # Y 方向渐变
        if y1 > 0:
            inside *= np.clip((yy - y1) / feather, 0, 1)
        if y2 < img_h:
            inside *= np.clip((y2 - yy) / feather, 0, 1)
        return inside

    elif mask_def["type"] == "outside":
        # 矩形区域外生效（用于车灯：只照亮窗外，不照亮室内）
        x1, y1, x2, y2 = mask_def["region"]
        feather = mask_def.get("feather", 50)
        outside = np.ones((img_h, img_w), dtype=np.float32)
        # 矩形内部衰减
        dx = np.clip((xx - x1) / feather, 0, 1) * np.clip((x2 - xx) / feather, 0, 1)
        dy = np.clip((yy - y1) / feather, 0, 1) * np.clip((y2 - yy) / feather, 0, 1)
        interior = dx * dy  # 矩形内部接近 1
        outside = 1.0 - interior * mask_def.get("block_strength", 0.9)
        return np.clip(outside, 0, 1)

    elif mask_def["type"] == "frustum":
        # 光锥：光从窗户玻璃射入室内，符合物理规律
        # 支持两种模式：
        #   1. mask_file: 用精确的窗户 mask PNG 作为透光口（推荐）
        #   2. aperture: 用矩形 + frame_width 内缩近似
        spread = mask_def.get("spread", 0.4)
        direction = mask_def.get("direction", "right")
        feather = float(mask_def.get("feather", 20))
        max_depth = float(mask_def.get("max_depth", 400))
        frame_w = float(mask_def.get("frame_width", 15))

        yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)
        mask = np.zeros((img_h, img_w), dtype=np.float32)

        # ── 确定透光口（mask 或矩形） ──
        mask_file = mask_def.get("mask_file")
        if mask_file:
            # 从 PNG 加载精确窗户 mask
            raw = cv2.imread(mask_file, cv2.IMREAD_GRAYSCALE)
            if raw is None:
                print(f"  ⚠️ Cannot load mask: {mask_file}")
                return mask
            # resize 到目标尺寸
            if raw.shape[:2] != (img_h, img_w):
                raw = cv2.resize(raw, (img_w, img_h), interpolation=cv2.INTER_NEAREST)
            glass_mask = (raw > 128).astype(np.float32)
            # 找 bounding box
            ys, xs = np.where(glass_mask > 0.5)
            if len(ys) == 0:
                return mask
            gx1, gx2 = float(xs.min()), float(xs.max())
            gy1, gy2 = float(ys.min()), float(ys.max())
        else:
            # 矩形 aperture 内缩 frame_w
            ax1, ay1, ax2, ay2 = [float(v) for v in mask_def["aperture"]]
            gx1, gy1 = ax1 + frame_w, ay1 + frame_w
            gx2, gy2 = ax2 - frame_w, ay2 - frame_w
            if gx2 <= gx1 or gy2 <= gy1:
                return mask
            glass_mask = np.zeros((img_h, img_w), dtype=np.float32)
            glass_mask[int(gy1):int(gy2), int(gx1):int(gx2)] = 1.0

        glass_cy = (gy1 + gy2) * 0.5
        glass_half_h = (gy2 - gy1) * 0.5
        glass_cx = (gx1 + gx2) * 0.5
        glass_half_w = (gx2 - gx1) * 0.5

        # ── 玻璃区域内的 feather（边缘渐变） ──
        glass_feather = float(mask_def.get("glass_feather", 8))
        dist_to_glass_edge = np.minimum(
            np.minimum(xx - gx1, gx2 - xx),
            np.minimum(yy - gy1, gy2 - yy)
        )
        glass_transmittance = np.clip(dist_to_glass_edge / glass_feather, 0, 1)
        glass_transmittance *= glass_mask  # 只在 mask 白区透光

        # ── 光锥扩散方向 ──
        if direction == "right":
            in_room = xx > gx2
            dist_from_glass = np.maximum(0, xx - gx2)
            dist_ratio = np.clip(dist_from_glass / max_depth, 0, 1)
            cone_half_h = glass_half_h * (1.0 + dist_ratio * spread * 2.5)
            cy_dist = np.abs(yy - glass_cy)
            vert_inside = np.clip((cone_half_h - cy_dist) / feather, 0, 1)
            horiz_strength = np.clip(1.0 - dist_ratio * 1.4, 0, 1)
            room_mask = vert_inside * horiz_strength
        elif direction == "left":
            in_room = xx < gx1
            dist_from_glass = np.maximum(0, gx1 - xx)
            dist_ratio = np.clip(dist_from_glass / max_depth, 0, 1)
            cone_half_h = glass_half_h * (1.0 + dist_ratio * spread * 2.5)
            cy_dist = np.abs(yy - glass_cy)
            vert_inside = np.clip((cone_half_h - cy_dist) / feather, 0, 1)
            horiz_strength = np.clip(1.0 - dist_ratio * 1.4, 0, 1)
            room_mask = vert_inside * horiz_strength
        elif direction == "down":
            in_room = yy > gy2
            dist_from_glass = np.maximum(0, yy - gy2)
            dist_ratio = np.clip(dist_from_glass / max_depth, 0, 1)
            cone_half_w = glass_half_w * (1.0 + dist_ratio * spread * 2.5)
            cx_dist = np.abs(xx - glass_cx)
            horiz_inside = np.clip((cone_half_w - cx_dist) / feather, 0, 1)
            vert_strength = np.clip(1.0 - dist_ratio * 1.4, 0, 1)
            room_mask = horiz_inside * vert_strength
        elif direction == "up":
            in_room = yy < gy1
            dist_from_glass = np.maximum(0, gy1 - yy)
            dist_ratio = np.clip(dist_from_glass / max_depth, 0, 1)
            cone_half_w = glass_half_w * (1.0 + dist_ratio * spread * 2.5)
            cx_dist = np.abs(xx - glass_cx)
            horiz_inside = np.clip((cone_half_w - cx_dist) / feather, 0, 1)
            vert_strength = np.clip(1.0 - dist_ratio * 1.4, 0, 1)
            room_mask = horiz_inside * vert_strength
        else:
            room_mask = np.zeros((img_h, img_w), dtype=np.float32)

        # 合成：玻璃区域 + 室内光锥
        mask = np.where(in_room, room_mask, 0.0)
        mask = np.where(glass_mask > 0.5, glass_transmittance, mask)

        return np.clip(mask, 0, 1)

    elif mask_def["type"] == "cone":
        # 锥形方向光：从光源位置出发，沿指定方向的锥形范围
        dx_dir, dy_dir = mask_def["dir"]
        angle_deg = mask_def.get("angle_deg", 60)
        feather_deg = mask_def.get("feather", 15)
        lx, ly = light_pos

        # 每个像素相对光源的方向
        pix_dx = xx - lx
        pix_dy = yy - ly
        pix_dist = np.sqrt(pix_dx**2 + pix_dy**2) + 1e-8

        # 光源方向向量归一化
        dir_len = np.sqrt(dx_dir**2 + dy_dir**2) + 1e-8
        dx_dir /= dir_len
        dy_dir /= dir_len

        # 夹角（度）
        cos_angle = (pix_dx * dx_dir + pix_dy * dy_dir) / pix_dist
        cos_angle = np.clip(cos_angle, -1, 1)
        angle = np.degrees(np.arccos(cos_angle))

        # 锥形内 + feather 渐变
        half = angle_deg / 2
        mask = np.clip((half - angle) / feather_deg, 0, 1)
        return mask

    elif mask_def["type"] == "radial":
        # 径向衰减：从指定中心向外衰减
        cx, cy = mask_def["center"]
        inner_r = mask_def.get("inner_radius", 0)
        outer_r = mask_def["radius"]
        dist = np.sqrt((xx - cx)**2 + (yy - cy)**2)
        mask = np.clip((outer_r - dist) / (outer_r - inner_r + 1e-8), 0, 1)
        return mask

    return np.ones((img_h, img_w), dtype=np.float32)


def get_mask_cache_key(mask_def):
    """生成 mask 缓存 key。"""
    return str(sorted(mask_def.items()))


# ── Depth Model ───────────────────────────────────────────────────

def load_depth_model():
    """Load Depth-Anything-V2-Large via transformers pipeline."""
    import torch
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
    """Compute per-pixel lighting for a single frame with light masks."""
    depth_float = depth_map.astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    total_light = np.zeros((img_h, img_w, 3), dtype=np.float32)
    total_light += scene_config.get("ambient", AMBIENT)

    for src in scene_config["lights"]:
        color = np.array(src["color"])
        r_min, r_max = src["intensity"]
        intensity = r_min + (r_max - r_min) * src["phase"](frame_idx, NUM_FRAMES)
        # vis_phase: 额外的可见性调制（如车灯只能在特定角度照到窗户）
        vp = src.get("vis_phase")
        if vp:
            intensity *= vp(frame_idx, NUM_FRAMES)

        # Light mask (support dynamic mask_phase for sweeping)
        mask_def = src.get("mask")
        if mask_def:
            lx = src["pos"][0] if "pos" in src else img_w // 2
            ly = src["pos"][1] if "pos" in src else img_h // 2
            # Apply mask_phase to shift the generated mask dynamically
            mp = src.get("mask_phase")
            if mp:
                t = mp["func"](frame_idx, NUM_FRAMES)
                lo, hi = mp["range"]
                offset = lo + (hi - lo) * t
                # Generate mask at original position, then shift the mask itself
                light_mask = generate_light_mask(mask_def, img_h, img_w, (lx, ly))
                # Roll the mask array along the specified axis
                shift_px = int(round(offset))
                if mp.get("axis", "x") == "x":
                    light_mask = np.roll(light_mask, shift_px, axis=1)
                    # Zero out wrapped-around region
                    if shift_px > 0:
                        light_mask[:, :shift_px] = 0
                    elif shift_px < 0:
                        light_mask[:, shift_px:] = 0
                else:
                    light_mask = np.roll(light_mask, shift_px, axis=0)
                    if shift_px > 0:
                        light_mask[:shift_px, :] = 0
                    elif shift_px < 0:
                        light_mask[shift_px:, :] = 0
            else:
                light_mask = generate_light_mask(mask_def, img_h, img_w, (lx, ly))
        else:
            light_mask = np.ones((img_h, img_w), dtype=np.float32)

        if src.get("distant"):
            # 方向光：平行光线，无距离衰减，无阴影，纯 mask 驱动
            # depth_factor 仍然生效（近处表面更亮）
            # dir_phase: 动态更新方向（车灯光源移动）
            dp = src.get("dir_phase")
            if dp:
                src["dir"] = dp(frame_idx, NUM_FRAMES)
                # 如果 frustum mask 用了 dir_key="auto"，同步更新扩散方向
                mask_def = src.get("mask", {})
                if mask_def.get("type") == "frustum" and mask_def.get("dir_key") == "auto":
                    d = src["dir"]
                    if abs(d[0]) > abs(d[1]):
                        mask_def["direction"] = "right" if d[0] > 0 else "left"
                    else:
                        mask_def["direction"] = "down" if d[1] > 0 else "up"
                    # 重新生成 mask（方向变了）
                    lx2 = src["pos"][0] if "pos" in src else img_w // 2
                    ly2 = src["pos"][1] if "pos" in src else img_h // 2
                    light_mask = generate_light_mask(mask_def, img_h, img_w, (lx2, ly2))
            depth_factor = 1.0 - depth_float
            contrib = (color[np.newaxis, np.newaxis, :] *
                       intensity *
                       depth_factor[:, :, np.newaxis] *
                       light_mask[:, :, np.newaxis])
        else:
            # 点光源：距离衰减 + 阴影 + mask
            lx, ly = src["pos"]
            radius = src["radius"]
            dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2)
            attenuation = 1.0 / (1.0 + (dist / radius) ** 2)
            depth_factor = 1.0 - depth_float
            # Light depth: use configured value, or sample depth map at light position
            light_depth = src.get("depth", None)
            if light_depth is None:
                lix = int(np.clip(lx, 0, img_w - 1))
                liy = int(np.clip(ly, 0, img_h - 1))
                light_depth = float(depth_float[liy, lix])
            shadow = ray_march_shadows(depth_float, (lx, ly), light_depth, img_h, img_w)
            contrib = (color[np.newaxis, np.newaxis, :] *
                       intensity *
                       attenuation[:, :, np.newaxis] *
                       depth_factor[:, :, np.newaxis] *
                       shadow[:, :, np.newaxis] *
                       light_mask[:, :, np.newaxis])

        total_light += contrib

    return np.clip(total_light, 0.0, 1.5)


def ray_march_shadows(depth_map, light_pos, light_depth, img_h, img_w):
    """March shadow rays from each pixel toward the light source.

    Tracks the shallowest surface encountered along the ray. A surface
    deeper than this minimum casts shadow on everything behind it.
    Surfaces that continue getting shallower do NOT block — light
    travels through progressively shallower regions freely.

    Examples (depth 0=near, 1=far):
      deep(0.7) → shallow(0.3) → shallower(0.1) : NOT blocked ✓
      deep(0.7) → shallow(0.3) → deep(0.6)      : blocked (wall behind)
      shallow(0.3) → deeper(0.5) → deeper(0.7)   : blocked (pixel blocks behind)

    Args:
        depth_map: (H,W) float32, 0=near, 1=far
        light_pos: (lx, ly) in pixel coords
        light_depth: z-depth of the light source (0-1)
        img_h, img_w: image dimensions
    """
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

    # Track the shallowest surface encountered along each ray.
    # Once a shallow surface is found, everything deeper behind it is shadowed.
    shallowest_so_far = depth_map.copy()

    blocker_threshold = 0.04

    for step in range(1, SHADOW_STEPS + 1):
        sx = np.clip(xx + dx_norm * step_dist * step, 0, img_w - 1).astype(np.int32)
        sy = np.clip(yy + dy_norm * step_dist * step, 0, img_h - 1).astype(np.int32)
        sampled_depth = depth_map[sy, sx]

        # A surface is shadowed if it's deeper than the shallowest surface
        # we've encountered so far along the ray — meaning something is
        # blocking the light path behind that shallow surface.
        diff = sampled_depth - shallowest_so_far
        shadow *= np.where(diff > blocker_threshold, 0.0, 1.0)

        # Update shallowest: only track shallower surfaces (lower depth)
        shallowest_so_far = np.minimum(shallowest_so_far, sampled_depth)

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
