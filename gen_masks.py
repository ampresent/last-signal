#!/usr/bin/env python3
"""
LAST SIGNAL - MobileSAM + Omni 视觉模型 Mask 生成器

流程:
  1. Omni 视觉模型识别场景中物体 → bbox
  2. MobileSAM (ONNX) 基于 bbox 生成精确 mask
  3. 叠层验证: Omni 审查生成的 mask 与原图是否一致

依赖: pip install onnxruntime pillow numpy opencv-python-headless requests

输出:
  - assets/masks/{scene}_{obj}_mask.png    单独物体 mask
  - assets/masks/{scene}_mask.png          组合 mask (交互区域并集)
  - assets/masks/{scene}_walkable_mask.png 可行走区域 mask
  - assets/masks/{scene}_water_mask.png    水面区域 mask (部分场景)
  - assets/masks/mask_metadata.json        元数据
"""

import cv2
import numpy as np
import json
import os
import sys
import subprocess
import base64
import io
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("⚠️  安装 pillow...")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--break-system-packages", "-q", "pillow"])
    from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    print("⚠️  安装 onnxruntime...")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--break-system-packages", "-q", "onnxruntime"])
    import onnxruntime as ort

# ── 常量 ──
IMG_W, IMG_H = 940, 627
GAME_W, GAME_H = 960, 640
MOBILESAM_INPUT = 1024  # MobileSAM 标准输入尺寸

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MASK_DIR = os.path.join(ASSETS_DIR, "masks")
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MASK_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# ── Omni API ──
MIMO_API_SCRIPT = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")

# ── MobileSAM ONNX 模型 ──
MOBILESAM_ONNX_URL = "https://hf-mirror.com/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx"
MOBILESAM_ONNX_PATH = os.path.join(MODELS_DIR, "mobile_sam_vit_t.onnx")

# ── 场景定义 (bbox 由 Omni 识别 + 人工微调) ──
SCENES = {
    "apartment": {
        "image": "bg_apartment.png",
        "objects": [
            {"id": "terminal", "label": "终端",
             "bbox": [500, 380, 900, 627]},
            {"id": "window", "label": "窗户",
             "bbox": [10, 140, 460, 590]},
            {"id": "door", "label": "门",
             "bbox": [760, 140, 938, 600]},
        ],
        "walkable": {"bbox": [60, 180, 900, 627], "label": "房间地面"},
        "water": None,
        "edge_transitions": [
            {"id": "to_street", "label": "出门", "zone": "bottom",
             "size": 50, "target": "street"},
        ]
    },
    "street": {
        "image": "bg_street.png",
        "objects": [
            {"id": "bar_entrance", "label": "The Rust 酒吧",
             "bbox": [80, 80, 380, 520]},
            {"id": "alley_entrance", "label": "小巷",
             "bbox": [0, 380, 140, 627]},
            {"id": "road_right", "label": "通往旧工业带",
             "bbox": [520, 80, 938, 520]},
            {"id": "dumpster", "label": "垃圾桶",
             "bbox": [350, 440, 540, 600]},
        ],
        "walkable": {"bbox": [30, 160, 930, 627], "label": "街道地面"},
        "water": {"bbox": [30, 480, 930, 627], "label": "路面积水"},
        "edge_transitions": [
            {"id": "to_alley", "label": "进入小巷", "zone": "left",
             "size": 50, "target": "alley"},
        ]
    },
    "bar": {
        "image": "bg_bar.png",
        "objects": [
            {"id": "bartender", "label": "酒保",
             "bbox": [420, 280, 700, 530]},
            {"id": "oracle", "label": "神秘客人",
             "bbox": [200, 300, 420, 560]},
            {"id": "exit", "label": "出口",
             "bbox": [760, 200, 938, 600]},
        ],
        "walkable": {"bbox": [60, 180, 900, 627], "label": "酒吧地面"},
        "water": None,
        "edge_transitions": []
    },
    "alley": {
        "image": "bg_alley.png",
        "objects": [
            {"id": "shadow", "label": "影子 (数据贩子)",
             "bbox": [230, 120, 520, 480]},
            {"id": "graffiti", "label": "涂鸦墙",
             "bbox": [10, 200, 230, 560]},
            {"id": "exit", "label": "返回街道",
             "bbox": [740, 300, 938, 627]},
        ],
        "walkable": {"bbox": [60, 120, 900, 627], "label": "巷子地面"},
        "water": {"bbox": [60, 460, 900, 627], "label": "巷子积水"},
        "edge_transitions": []
    },
    "tower": {
        "image": "bg_tower_exterior.png",
        "objects": [
            {"id": "scanner", "label": "正门扫描仪",
             "bbox": [380, 350, 620, 610]},
            {"id": "guard_booth", "label": "警卫亭",
             "bbox": [220, 480, 420, 620]},
            {"id": "exit", "label": "返回街道",
             "bbox": [780, 400, 938, 627]},
        ],
        "walkable": {"bbox": [100, 200, 900, 627], "label": "塔楼广场地面"},
        "water": {"bbox": [100, 500, 900, 627], "label": "广场积水"},
        "edge_transitions": []
    },
    "server": {
        "image": "bg_server_room.png",
        "objects": [
            {"id": "terminal", "label": "终端",
             "bbox": [235, 200, 720, 520]},
            {"id": "rack", "label": "服务器机柜",
             "bbox": [0, 0, 240, 627]},
            {"id": "rooftop_exit", "label": "通往楼顶",
             "bbox": [380, 400, 600, 627]},
            {"id": "lobby_exit", "label": "返回大厅",
             "bbox": [0, 500, 250, 627]},
        ],
        "walkable": {"bbox": [60, 100, 900, 627], "label": "机房地面"},
        "water": None,
        "edge_transitions": []
    },
    "rooftop": {
        "image": "bg_rooftop.png",
        "objects": [],
        "walkable": {"bbox": [60, 100, 900, 627], "label": "楼顶地面"},
        "water": {"bbox": [60, 480, 900, 627], "label": "楼顶积水"},
        "edge_transitions": [
            {"id": "to_server", "label": "下楼", "zone": "bottom",
             "size": 60, "target": "server"},
        ]
    },
    "office": {
        "image": "bg_office.png",
        "objects": [
            {"id": "terminal", "label": "终端",
             "bbox": [250, 200, 600, 580]},
            {"id": "safe", "label": "保险柜",
             "bbox": [750, 280, 938, 620]},
            {"id": "chair", "label": "办公椅",
             "bbox": [640, 380, 830, 620]},
        ],
        "walkable": {"bbox": [60, 140, 900, 627], "label": "办公室地面"},
        "water": None,
        "edge_transitions": []
    },
    "echo_lobby": {
        "image": "bg_echo_lobby.png",
        "objects": [
            {"id": "reception", "label": "前台接待",
             "bbox": [300, 280, 660, 500]},
            {"id": "scanner", "label": "安检门",
             "bbox": [350, 400, 610, 627]},
            {"id": "elevator", "label": "电梯",
             "bbox": [740, 200, 938, 520]},
            {"id": "guard_post", "label": "警卫亭",
             "bbox": [50, 350, 280, 560]},
            {"id": "exit", "label": "出口",
             "bbox": [0, 500, 200, 627]},
        ],
        "walkable": {"bbox": [30, 180, 930, 627], "label": "大厅地面"},
        "water": None,
        "edge_transitions": [
            {"id": "to_maintenance", "label": "地下通道", "zone": "bottom",
             "size": 40, "target": "maintenance"},
        ]
    },
    "maintenance": {
        "image": "bg_maintenance.png",
        "objects": [
            {"id": "blast_door", "label": "防爆门",
             "bbox": [350, 150, 610, 500]},
            {"id": "pipe_valve", "label": "管道阀门",
             "bbox": [80, 250, 280, 480]},
            {"id": "warning_sign", "label": "警告标志",
             "bbox": [650, 100, 850, 320]},
            {"id": "exit", "label": "返回大厅",
             "bbox": [0, 500, 200, 627]},
        ],
        "walkable": {"bbox": [30, 100, 930, 627], "label": "通道地面"},
        "water": {"bbox": [30, 480, 930, 627], "label": "通道积水"},
        "edge_transitions": []
    },
    "data_haven": {
        "image": "bg_data_haven.png",
        "objects": [
            {"id": "workstation", "label": "工作站",
             "bbox": [200, 200, 550, 480]},
            {"id": "train_car", "label": "旧列车",
             "bbox": [700, 280, 938, 580]},
            {"id": "antenna", "label": "天线阵列",
             "bbox": [350, 20, 600, 180]},
            {"id": "exit", "label": "出口",
             "bbox": [0, 500, 200, 627]},
        ],
        "walkable": {"bbox": [30, 100, 930, 627], "label": "站台地面"},
        "water": None,
        "edge_transitions": []
    },
    "flashback": {
        "image": "bg_flashback.png",
        "objects": [
            {"id": "pod_3", "label": "3号实验舱",
             "bbox": [250, 250, 480, 520]},
            {"id": "monitor", "label": "监控屏",
             "bbox": [550, 150, 780, 400]},
            {"id": "terminal", "label": "控制台",
             "bbox": [100, 380, 350, 580]},
        ],
        "walkable": {"bbox": [60, 140, 900, 627], "label": "实验室地面"},
        "water": None,
        "edge_transitions": []
    },
    "hospital": {
        "image": "bg_hospital.png",
        "objects": [
            {"id": "room_door", "label": "病房门",
             "bbox": [100, 200, 350, 520]},
            {"id": "window", "label": "窗户",
             "bbox": [650, 100, 938, 480]},
            {"id": "nurse_station", "label": "护士站",
             "bbox": [400, 300, 600, 500]},
        ],
        "walkable": {"bbox": [30, 120, 930, 627], "label": "走廊地面"},
        "water": None,
        "edge_transitions": [
            {"id": "to_street", "label": "出院", "zone": "bottom",
             "size": 50, "target": "street"},
        ]
    },
}


# ════════════════════════════════════════════════
# MobileSAM ONNX 推理
# ════════════════════════════════════════════════

class MobileSAM:
    """MobileSAM ONNX 推理器 (encoder + decoder 联合模型)."""

    def __init__(self, model_path):
        print(f"  📦 加载 MobileSAM: {model_path}")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(model_path, opts,
                                            providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        print(f"  ✓ MobileSAM 就绪 (inputs: {self.input_name})")

    def preprocess_image(self, img_bgr):
        """预处理图片: BGR→RGB, resize, normalize."""
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]

        # resize 到 1024x1024 (MobileSAM 标准输入)
        scale = MOBILESAM_INPUT / max(orig_h, orig_w)
        new_h, new_w = int(orig_h * scale), int(orig_w * scale)
        img_resized = cv2.resize(img_rgb, (new_w, new_h),
                                 interpolation=cv2.INTER_LINEAR)

        # pad 到 1024x1024
        padded = np.zeros((MOBILESAM_INPUT, MOBILESAM_INPUT, 3), dtype=np.uint8)
        padded[:new_h, :new_w, :] = img_resized

        # normalize: (pixel / 255 - mean) / std
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (padded.astype(np.float32) / 255.0 - mean) / std

        # NCHW
        tensor = normalized.transpose(2, 0, 1)[np.newaxis, ...]
        return tensor.astype(np.float32), scale, (orig_h, orig_w)

    def segment_with_box(self, img_bgr, bbox):
        """
        使用 bbox 作为 prompt 进行分割。
        bbox: [x1, y1, x2, y2] 基于原图坐标。
        返回: binary mask (原图尺寸, uint8, 0/255)
        """
        input_tensor, scale, (orig_h, orig_w) = self.preprocess_image(img_bgr)

        # 将 bbox 转换到 1024x1024 坐标
        x1, y1, x2, y2 = bbox
        box_scaled = np.array([[x1 * scale, y1 * scale,
                                 x2 * scale, y2 * scale]],
                               dtype=np.float32)

        try:
            outputs = self.session.run(self.output_names, {
                self.input_name: input_tensor,
                "box_prompt": box_scaled,
            })
        except Exception as e:
            # 不同的 ONNX 模型可能有不同的输入名
            # 尝试用 point_prompt
            try:
                # 用 bbox 中心点作为 point prompt
                cx = (x1 + x2) / 2 * scale
                cy = (y1 + y2) / 2 * scale
                point = np.array([[cx, cy]], dtype=np.float32)
                label = np.array([1], dtype=np.int32)

                outputs = self.session.run(self.output_names, {
                    self.input_name: input_tensor,
                    "point_coords": point,
                    "point_labels": label,
                })
            except Exception as e2:
                print(f"    ⚠️  MobileSAM 推理失败: {e2}")
                # fallback: 返回 bbox 矩形 mask
                mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
                mask[y1:y2, x1:x2] = 255
                return mask

        # 找到 mask 输出 (通常是最后一个, shape [1, 1, H, W] 或 [1, N, H, W])
        mask_output = None
        for out in outputs:
            if out.ndim >= 3 and out.shape[-1] == MOBILESAM_INPUT:
                mask_output = out
                break

        if mask_output is None:
            # fallback
            mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
            mask[y1:y2, x1:x2] = 255
            return mask

        # 取第一个 mask, sigmoid, 阈值化
        if mask_output.ndim == 4:
            mask_logits = mask_output[0, 0]  # [H, W]
        else:
            mask_logits = mask_output[0]

        # sigmoid
        mask_prob = 1.0 / (1.0 + np.exp(-np.clip(mask_logits, -50, 50)))

        # resize 回原图尺寸
        mask_resized = cv2.resize(mask_prob, (orig_w, orig_h),
                                  interpolation=cv2.INTER_LINEAR)

        # 阈值化 + 形态学清理
        binary = (mask_resized > 0.5).astype(np.uint8) * 255
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

        return binary


def download_mobilesam():
    """下载 MobileSAM ONNX 模型 (如不存在)."""
    if os.path.exists(MOBILESAM_ONNX_PATH):
        print(f"  ✓ MobileSAM 已存在: {MOBILESAM_ONNX_PATH}")
        return True

    print(f"  ⬇️  下载 MobileSAM ONNX 模型...")
    import urllib.request

    mirrors = [
        MOBILESAM_ONNX_URL,
        "https://huggingface.co/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx",
    ]

    for url in mirrors:
        try:
            print(f"     {url}")
            urllib.request.urlretrieve(url, MOBILESAM_ONNX_PATH)
            size_mb = os.path.getsize(MOBILESAM_ONNX_PATH) / 1024 / 1024
            print(f"  ✓ 下载完成: {size_mb:.1f}MB")
            return True
        except Exception as e:
            print(f"     ❌ 失败: {e}")
            continue

    print("  ❌ MobileSAM 下载失败, 将使用 GrabCut 降级方案")
    return False


# ════════════════════════════════════════════════
# Omni 视觉模型 (mimo-omni)
# ════════════════════════════════════════════════

def omni_analyze_image(image_path, prompt, max_tokens=4096):
    """调用 mimo-omni 分析图片."""
    if not os.path.exists(MIMO_API_SCRIPT):
        print("    ⚠️  mimo-omni 不可用, 跳过视觉分析")
        return None

    try:
        result = subprocess.run(
            ["bash", MIMO_API_SCRIPT, "image", image_path, prompt,
             "--max-tokens", str(max_tokens)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception as e:
        print(f"    ⚠️  Omni 调用失败: {e}")
        return None


def omni_detect_objects(image_path, scene_id):
    """
    Step 1: 用 Omni 识别场景中的可交互物体.
    返回: [{"id": str, "label": str, "bbox": [x1,y1,x2,y2]}, ...]
    """
    prompt = (
        "你是一个游戏场景分析器。这张图是 2D 冒险游戏的场景背景 (940x627 像素)。\n"
        "请识别所有可交互的物体/区域，并为每个物体返回精确的边界框。\n\n"
        "返回 JSON 数组格式:\n"
        '[{"id": "英文标识", "label": "中文名", "bbox": [x1, y1, x2, y2]}]\n\n'
        "注意:\n"
        "- id 用小写英文, 如 terminal, door, window\n"
        "- bbox 是像素坐标 [左上x, 左上y, 右下x, 右下y]\n"
        "- 只返回 JSON, 不要其他文字\n"
        "- 尽量精确, bbox 紧贴物体边缘\n"
    )
    response = omni_analyze_image(image_path, prompt)
    if not response:
        return None

    try:
        # 提取 JSON
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            objects = json.loads(json_match.group())
            return objects
    except json.JSONDecodeError:
        pass
    return None


def omni_verify_mask(image_path, mask_path, obj_label, scene_id):
    """
    Step 3 (叠层验证): 用 Omni 检查 mask 是否准确覆盖了目标物体.
    返回: (passed: bool, reason: str)
    """
    # 创建叠加预览图
    img = cv2.imread(image_path)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if img is None or mask is None:
        return True, "无法读取文件, 跳过验证"

    # 将 mask 缩放到图片尺寸
    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    # 创建红色半透明叠加
    overlay = img.copy()
    overlay[mask > 128] = [0, 0, 200]  # BGR: 红色
    blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)

    # 保存临时预览图
    preview_path = os.path.join(MASK_DIR, "_verify_preview.png")
    cv2.imwrite(preview_path, blended)

    prompt = (
        f"这是游戏场景 '{scene_id}' 的物体 '{obj_label}' 的 mask 验证图。\n"
        "红色半透明区域是生成的 mask。\n\n"
        "请判断:\n"
        "1. mask 是否准确覆盖了目标物体? (是/否)\n"
        "2. mask 是否包含过多背景区域? (是/否)\n"
        "3. mask 是否遗漏了物体的重要部分? (是/否)\n\n"
        "如果 mask 质量合格, 回复: PASS\n"
        "如果 mask 质量不合格, 回复: FAIL <原因>\n"
        "只回复 PASS 或 FAIL, 不要其他文字。"
    )
    response = omni_analyze_image(preview_path, prompt)
    if not response:
        return True, "Omni 未响应, 默认通过"

    if "PASS" in response.upper():
        return True, "验证通过"
    else:
        reason = response.replace("FAIL", "").strip()
        return False, reason


# ════════════════════════════════════════════════
# GrabCut 降级方案
# ════════════════════════════════════════════════

def grabcut_segment(img, bbox, iter_count=5):
    """GrabCut 精细分割 (降级方案)."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, w - 2))
    y1 = max(0, min(y1, h - 2))
    x2 = max(x1 + 2, min(x2, w))
    y2 = max(y1 + 2, min(y2, h))

    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(img, mask, (x1, y1, x2 - x1, y2 - y1),
                     bgd_model, fgd_model, iter_count, cv2.GC_INIT_WITH_RECT)
        result = np.where(
            (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    except cv2.error:
        result = np.zeros((h, w), np.uint8)
        result[y1:y2, x1:x2] = 255
        return result

    result = cv2.morphologyEx(result, cv2.MORPH_CLOSE,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    result = cv2.morphologyEx(result, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    result = cv2.GaussianBlur(result, (5, 5), 0)
    _, result = cv2.threshold(result, 127, 255, cv2.THRESH_BINARY)
    return result


# ════════════════════════════════════════════════
# 场景处理
# ════════════════════════════════════════════════

def find_scene_image(image_name):
    """查找场景图片 (支持 png/webp)."""
    base = os.path.splitext(image_name)[0]
    for ext in [".png", ".webp"]:
        path = os.path.join(ASSETS_DIR, base + ext)
        if os.path.exists(path):
            return path
    return None


def add_edge_transition(mask, zone, size, w, h):
    """在 mask 指定边缘添加过渡区域."""
    if zone == "bottom":
        mask[h - size:h, :] = 255
    elif zone == "top":
        mask[0:size, :] = 255
    elif zone == "left":
        mask[:, 0:size] = 255
    elif zone == "right":
        mask[:, w - size:w] = 255


def process_scene(scene_id, data, sam_model, skip_omni_detect=False):
    """
    处理单个场景.
    skip_omni_detect: True 时跳过 Omni 识别, 直接用 SCENES 中的 bbox.
    """
    img_path = find_scene_image(data["image"])
    if not img_path:
        print(f"  ❌ 图片不存在: {data['image']}")
        return False

    img = cv2.imread(img_path)
    if img is None:
        print(f"  ❌ 无法读取: {img_path}")
        return False

    h, w = img.shape[:2]
    combined = np.zeros((h, w), np.uint8)
    all_passed = True

    # ── Step 1: Omni 识别物体 (可选, 已有 bbox 时跳过) ──
    objects = data["objects"]
    if not skip_omni_detect and objects:
        print(f"  🔍 Omni 识别物体...")
        detected = omni_detect_objects(img_path, scene_id)
        if detected:
            print(f"  ✓ Omni 识别到 {len(detected)} 个物体")
            # 合并: 优先用 Omni 的 bbox, 但保留 SCENES 中的 id/label
            for obj in objects:
                for det in detected:
                    if det.get("id", "").lower() == obj["id"].lower():
                        obj["bbox"] = det["bbox"]
                        break

    # ── Step 2: MobileSAM 分割每个物体 ──
    for obj in objects:
        bbox = obj["bbox"]
        label = obj["label"]
        obj_id = obj["id"]

        if sam_model:
            seg = sam_model.segment_with_box(img, bbox)
        else:
            seg = grabcut_segment(img, bbox)

        ratio = np.count_nonzero(seg) / (h * w) * 100

        # 质量检查 + fallback
        if ratio < 0.05:
            print(f"    ⚠️  {label}: mask 太小 ({ratio:.2f}%), 使用矩形 fallback")
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = bbox
            seg[y1:y2, x1:x2] = 255
        elif ratio > 35:
            print(f"    ⚠️  {label}: mask 太大 ({ratio:.1f}%), 缩小 bbox 重试")
            x1, y1, x2, y2 = bbox
            mx, my = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            if sam_model:
                seg = sam_model.segment_with_box(img, [x1+mx, y1+my, x2-mx, y2-my])
            else:
                seg = grabcut_segment(img, [x1+mx, y1+my, x2-mx, y2-my])
            s2_ratio = np.count_nonzero(seg) / (h * w) * 100
            if not (0.05 < s2_ratio < 35):
                seg = np.zeros((h, w), np.uint8)
                seg[y1:y2, x1:x2] = 255

        # 保存单独 mask (缩放到游戏尺寸)
        obj_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj_id}_mask.png")
        cv2.imwrite(mask_path, obj_game)

        combined = cv2.bitwise_or(combined, seg)
        print(f"  🎯 {label} ({obj_id}): {ratio:.1f}%")

    # ── Walkable 区域 ──
    walkable_cfg = data.get("walkable")
    if walkable_cfg:
        if sam_model:
            seg = sam_model.segment_with_box(img, walkable_cfg["bbox"])
        else:
            seg = grabcut_segment(img, walkable_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 1.0:
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = walkable_cfg["bbox"]
            seg[y1:y2, x1:x2] = 255
        # 减去障碍物 mask
        for obj in data["objects"]:
            obj_mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png")
            if os.path.exists(obj_mask_path):
                obs = cv2.imread(obj_mask_path, cv2.IMREAD_GRAYSCALE)
                if obs is not None:
                    obs = cv2.resize(obs, (w, h), interpolation=cv2.INTER_NEAREST)
                    seg[obs > 128] = 0
        seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        seg = cv2.morphologyEx(seg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        walkable_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.png"), walkable_game)
        walk_pct = np.count_nonzero(walkable_game) / (GAME_W * GAME_H) * 100
        print(f"  🚶 walkable ({walkable_cfg['label']}): {walk_pct:.1f}%")

    # ── Water 水面区域 ──
    water_cfg = data.get("water")
    if water_cfg:
        if sam_model:
            seg = sam_model.segment_with_box(img, water_cfg["bbox"])
        else:
            seg = grabcut_segment(img, water_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 0.3:
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = water_cfg["bbox"]
            seg[y1:y2, x1:x2] = 255
        seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        seg = cv2.morphologyEx(seg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        water_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_water_mask.png"), water_game)
        water_pct = np.count_nonzero(water_game) / (GAME_W * GAME_H) * 100
        print(f"  💧 water ({water_cfg['label']}): {water_pct:.1f}%")

    # 边缘过渡
    for edge in data.get("edge_transitions", []):
        add_edge_transition(combined, edge["zone"], edge["size"], w, h)
        print(f"  🚪 边缘过渡: {edge['label']} ({edge['zone']})")

    # 保存组合 mask
    combined_game = cv2.resize(combined, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_mask.png"), combined_game)
    total_pct = np.count_nonzero(combined_game) / (GAME_W * GAME_H) * 100
    print(f"  💾 {scene_id}_mask.png ({total_pct:.1f}% 覆盖)")

    # ── Step 3: 叠层验证 (Omni 审查) ──
    if objects:
        print(f"  🔎 叠层验证 ({len(objects)} 个物体)...")
        for obj in objects:
            mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png")
            if os.path.exists(mask_path):
                passed, reason = omni_verify_mask(img_path, mask_path,
                                                   obj["label"], scene_id)
                status = "✅" if passed else "❌"
                print(f"    {status} {obj['label']}: {reason}")
                if not passed:
                    all_passed = False

    return all_passed


def save_metadata():
    """保存 mask_metadata.json."""
    meta = {}
    for sid, sd in SCENES.items():
        objects = [
            {"id": o["id"], "label": o["label"],
             "mask": f"masks/{sid}_{o['id']}_mask.png"}
            for o in sd["objects"]
        ]
        if sd.get("walkable"):
            objects.append({
                "id": "walkable", "label": sd["walkable"]["label"],
                "mask": f"masks/{sid}_walkable_mask.png",
                "type": "walkable"
            })
        if sd.get("water"):
            objects.append({
                "id": "water", "label": sd["water"]["label"],
                "mask": f"masks/{sid}_water_mask.png",
                "type": "water"
            })
        meta[sid] = {
            "objects": objects,
            "edge_transitions": [
                {"id": e["id"], "label": e["label"],
                 "zone": e["zone"], "target": e.get("target", "")}
                for e in sd.get("edge_transitions", [])
            ]
        }
    with open(os.path.join(MASK_DIR, "mask_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def git_commit_and_push(scene_id, obj_id=None):
    """提交并推送单个 mask."""
    if obj_id:
        msg = f"mask: {scene_id}/{obj_id}"
    else:
        msg = f"mask: {scene_id} all masks"

    try:
        subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, check=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, check=True)
        subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)
        print(f"  📤 pushed: {msg}")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️  git push 失败: {e}")


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LAST SIGNAL - MobileSAM Mask 生成器")
    parser.add_argument("--scene", help="只处理指定场景")
    parser.add_argument("--skip-verify", action="store_true",
                        help="跳过 Omni 叠层验证")
    parser.add_argument("--skip-omni-detect", action="store_true",
                        help="跳过 Omni 物体识别, 直接用 SCENES 中的 bbox")
    parser.add_argument("--no-push", action="store_true",
                        help="不自动 git push")
    parser.add_argument("--grabcut-only", action="store_true",
                        help="不使用 MobileSAM, 只用 GrabCut")
    args = parser.parse_args()

    print("=" * 60)
    print("🎭 LAST SIGNAL - MobileSAM + Omni Mask 生成器")
    print("=" * 60)

    # ── 下载 MobileSAM ──
    sam_model = None
    if not args.grabcut_only:
        if download_mobilesam():
            try:
                sam_model = MobileSAM(MOBILESAM_ONNX_PATH)
            except Exception as e:
                print(f"  ⚠️  MobileSAM 加载失败: {e}")
                print(f"  ↩️  降级到 GrabCut")

    if sam_model is None:
        print("  ℹ️  使用 GrabCut 模式")

    # ── 处理场景 ──
    scenes_to_process = SCENES
    if args.scene:
        if args.scene not in SCENES:
            print(f"❌ 未知场景: {args.scene}")
            print(f"   可用: {', '.join(SCENES.keys())}")
            sys.exit(1)
        scenes_to_process = {args.scene: SCENES[args.scene]}

    for scene_id, data in scenes_to_process.items():
        print(f"\n{'─'*50}")
        print(f"🎬 {scene_id}")
        print(f"{'─'*50}")

        ok = process_scene(scene_id, data, sam_model,
                           skip_omni_detect=args.skip_omni_detect)

        if not args.no_push:
            git_commit_and_push(scene_id)

    # ── 保存元数据 ──
    save_metadata()
    if not args.no_push:
        git_commit_and_push("_metadata")

    total_obj = sum(len(s["objects"]) for s in SCENES.values())
    total_edge = sum(len(s.get("edge_transitions", [])) for s in SCENES.values())
    print(f"\n{'='*60}")
    print(f"✅ 完成: {total_obj} 个物体 + {total_edge} 个边缘过渡")
    print(f"📁 {MASK_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
