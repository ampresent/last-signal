#!/usr/bin/env python3
"""
LAST SIGNAL - MobileSAM + Omni 视觉模型 Mask 生成器

严格模式: 无降级策略。所有模型必须可用，否则直接报错退出。

流程:
  1. Omni 视觉模型识别场景中物体 → bbox (可跳过, 使用预定义 bbox)
  2. MobileSAM (ONNX encoder + decoder) 基于 bbox 生成精确 mask
  3. 叠层验证: Omni 审查生成的 mask 与原图是否一致

依赖: onnxruntime, pillow, numpy, opencv-python-headless
模型: models/mobilesam.encoder.onnx + models/mobile_sam.onnx (必须存在)
"""

import cv2
import numpy as np
import json
import os
import sys
import subprocess
import time
from pathlib import Path

from PIL import Image
import onnxruntime as ort

# ── 常量 ──
IMG_W, IMG_H = 940, 627
GAME_W, GAME_H = 960, 640
MOBILESAM_SIZE = 1024  # MobileSAM 标准输入尺寸

# ImageNet 归一化参数
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MASK_DIR = os.path.join(ASSETS_DIR, "masks")
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MASK_DIR, exist_ok=True)

# ── Omni API ──
MIMO_API_SCRIPT = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")

# ── MobileSAM 模型路径 (必须存在) ──
ENCODER_PATH = os.path.join(MODELS_DIR, "mobilesam.encoder.onnx")
DECODER_PATH = os.path.join(MODELS_DIR, "mobile_sam.onnx")


# ════════════════════════════════════════════════
# 场景定义
# ════════════════════════════════════════════════

SCENES = {
    "apartment": {
        "image": "bg_apartment.png",
        "spawn": [0.48, 0.78],  # 归一化坐标, walkable 区域中心
        "objects": [
            {"id": "terminal", "label": "终端", "bbox": [500, 380, 900, 627]},
            {"id": "window", "label": "窗户", "bbox": [10, 140, 460, 590]},
            {"id": "door", "label": "门", "bbox": [760, 140, 938, 600]},
        ],
        "walkable": {"bbox": [60, 400, 900, 627], "label": "房间地面"},
        "water": None,
        "edge_transitions": [
            {"id": "to_street", "label": "出门", "zone": "bottom",
             "size": 50, "target": "street"},
        ]
    },
    "street": {
        "image": "bg_street.png",
        "spawn": [0.48, 0.64],
        "objects": [
            {"id": "bar_entrance", "label": "The Rust 酒吧", "bbox": [80, 80, 380, 520]},
            {"id": "alley_entrance", "label": "小巷", "bbox": [0, 380, 140, 627]},
            {"id": "road_right", "label": "通往旧工业带", "bbox": [520, 80, 938, 520]},
            {"id": "dumpster", "label": "垃圾桶", "bbox": [350, 440, 540, 600]},
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
        "spawn": [0.51, 0.79],
        "objects": [
            {"id": "bartender", "label": "酒保", "bbox": [420, 280, 700, 530]},
            {"id": "oracle", "label": "神秘客人", "bbox": [200, 300, 420, 560]},
            {"id": "exit", "label": "出口", "bbox": [760, 200, 938, 600]},
        ],
        "walkable": {"bbox": [60, 180, 900, 627], "label": "酒吧地面"},
        "water": None,
        "edge_transitions": []
    },
    "alley": {
        "image": "bg_alley.png",
        "spawn": [0.57, 0.77],
        "objects": [
            {"id": "shadow", "label": "影子 (数据贩子)", "bbox": [230, 120, 520, 480]},
            {"id": "graffiti", "label": "涂鸦墙", "bbox": [10, 200, 230, 560]},
            {"id": "exit", "label": "返回街道", "bbox": [740, 300, 938, 627]},
        ],
        "walkable": {"bbox": [60, 120, 900, 627], "label": "巷子地面"},
        "water": {"bbox": [60, 460, 900, 627], "label": "巷子积水"},
        "edge_transitions": []
    },
    "tower": {
        "image": "bg_tower_exterior.png",
        "spawn": [0.51, 0.63],
        "objects": [
            {"id": "scanner", "label": "正门扫描仪", "bbox": [380, 350, 620, 610]},
            {"id": "guard_booth", "label": "警卫亭", "bbox": [220, 480, 420, 620]},
            {"id": "exit", "label": "返回街道", "bbox": [780, 400, 938, 627]},
        ],
        "walkable": {"bbox": [100, 200, 900, 627], "label": "塔楼广场地面"},
        "water": {"bbox": [100, 500, 900, 627], "label": "广场积水"},
        "edge_transitions": []
    },
    "server": {
        "image": "bg_server_room.png",
        "spawn": [0.39, 0.87],
        "objects": [
            {"id": "terminal", "label": "终端", "bbox": [235, 200, 720, 520]},
            {"id": "rack", "label": "服务器机柜", "bbox": [0, 0, 240, 627]},
            {"id": "rooftop_exit", "label": "通往楼顶", "bbox": [380, 400, 600, 627]},
            {"id": "lobby_exit", "label": "返回大厅", "bbox": [0, 500, 250, 627]},
        ],
        "walkable": {"bbox": [60, 100, 900, 627], "label": "机房地面"},
        "water": None,
        "edge_transitions": []
    },
    "rooftop": {
        "image": "bg_rooftop.png",
        "spawn": [0.50, 0.70],
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
        "spawn": [0.56, 0.76],
        "objects": [
            {"id": "terminal", "label": "终端", "bbox": [250, 200, 600, 580]},
            {"id": "safe", "label": "保险柜", "bbox": [750, 280, 938, 620]},
            {"id": "chair", "label": "办公椅", "bbox": [640, 380, 830, 620]},
        ],
        "walkable": {"bbox": [60, 140, 900, 627], "label": "办公室地面"},
        "water": None,
        "edge_transitions": []
    },
    "echo_lobby": {
        "image": "bg_echo_lobby.png",
        "spawn": [0.35, 0.84],
        "objects": [
            {"id": "reception", "label": "前台接待", "bbox": [300, 280, 660, 500]},
            {"id": "scanner", "label": "安检门", "bbox": [350, 400, 610, 627]},
            {"id": "elevator", "label": "电梯", "bbox": [740, 200, 938, 520]},
            {"id": "guard_post", "label": "警卫亭", "bbox": [50, 350, 280, 560]},
            {"id": "exit", "label": "出口", "bbox": [0, 500, 200, 627]},
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
        "spawn": [0.48, 0.81],
        "objects": [
            {"id": "blast_door", "label": "防爆门", "bbox": [350, 150, 610, 500]},
            {"id": "pipe_valve", "label": "管道阀门", "bbox": [80, 250, 280, 480]},
            {"id": "warning_sign", "label": "警告标志", "bbox": [650, 100, 850, 320]},
            {"id": "exit", "label": "返回大厅", "bbox": [0, 500, 200, 627]},
        ],
        "walkable": {"bbox": [30, 100, 930, 627], "label": "通道地面"},
        "water": {"bbox": [30, 480, 930, 627], "label": "通道积水"},
        "edge_transitions": []
    },
    "data_haven": {
        "image": "bg_data_haven.png",
        "spawn": [0.58, 0.78],
        "objects": [
            {"id": "workstation", "label": "工作站", "bbox": [200, 200, 550, 480]},
            {"id": "train_car", "label": "旧列车", "bbox": [700, 280, 938, 580]},
            {"id": "antenna", "label": "天线阵列", "bbox": [350, 20, 600, 180]},
            {"id": "exit", "label": "出口", "bbox": [0, 500, 200, 627]},
        ],
        "walkable": {"bbox": [30, 100, 930, 627], "label": "站台地面"},
        "water": None,
        "edge_transitions": []
    },
    "flashback": {
        "image": "bg_flashback.png",
        "spawn": [0.55, 0.76],
        "objects": [
            {"id": "pod_3", "label": "3号实验舱", "bbox": [250, 250, 480, 520]},
            {"id": "monitor", "label": "监控屏", "bbox": [550, 150, 780, 400]},
            {"id": "terminal", "label": "控制台", "bbox": [100, 380, 350, 580]},
        ],
        "walkable": {"bbox": [60, 140, 900, 627], "label": "实验室地面"},
        "water": None,
        "edge_transitions": []
    },
    "hospital": {
        "image": "bg_hospital.png",
        "spawn": [0.47, 0.79],
        "objects": [
            {"id": "room_door", "label": "病房门", "bbox": [100, 200, 350, 520]},
            {"id": "window", "label": "窗户", "bbox": [650, 100, 938, 480]},
            {"id": "nurse_station", "label": "护士站", "bbox": [400, 300, 600, 500]},
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
# MobileSAM ONNX (encoder + decoder, 严格模式)
# ════════════════════════════════════════════════

class MobileSAM:
    """MobileSAM ONNX 推理器: encoder + decoder, 无降级."""

    def __init__(self):
        # 检查模型文件
        if not os.path.isfile(ENCODER_PATH):
            raise FileNotFoundError(
                f"MobileSAM encoder 不存在: {ENCODER_PATH}\n"
                f"请运行: bash setup.sh 或手动下载:\n"
                f"  curl -L https://hf-mirror.com/PulpCut/mobilesam-onnx/resolve/main/mobilesam.encoder.onnx "
                f"-o {ENCODER_PATH}")
        if not os.path.isfile(DECODER_PATH):
            raise FileNotFoundError(
                f"MobileSAM decoder 不存在: {DECODER_PATH}\n"
                f"请运行: bash setup.sh 或手动下载:\n"
                f"  curl -L https://hf-mirror.com/PulpCut/mobilesam-onnx/resolve/main/mobile_sam.onnx "
                f"-o {DECODER_PATH}")

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2

        print(f"  📦 加载 encoder: {ENCODER_PATH}")
        self.encoder = ort.InferenceSession(ENCODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  📦 加载 decoder: {DECODER_PATH}")
        self.decoder = ort.InferenceSession(DECODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  ✓ MobileSAM 就绪")

    def _preprocess(self, img_bgr):
        """BGR→RGB, resize to 1024 max, normalize. encoder 需要 HWC, decoder 需要 embeddings."""
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]

        scale = MOBILESAM_SIZE / max(orig_h, orig_w)
        new_h, new_w = int(orig_h * scale), int(orig_w * scale)
        resized = cv2.resize(img_rgb, (new_w, new_h),
                             interpolation=cv2.INTER_LINEAR)

        padded = np.zeros((MOBILESAM_SIZE, MOBILESAM_SIZE, 3), dtype=np.uint8)
        padded[:new_h, :new_w, :] = resized

        normalized = (padded.astype(np.float32) / 255.0 - MEAN) / STD
        # encoder 期望 HWC [1024, 1024, 3]
        return normalized, scale, (orig_h, orig_w)

    def _encode(self, input_hwc):
        """Image encoder → image embeddings. 输入 HWC [1024,1024,3]."""
        return self.encoder.run(None, {"input_image": input_hwc})[0]

    def _decode(self, image_embeddings, scale, orig_size, bbox):
        """Mask decoder: bbox prompt → binary mask."""
        orig_h, orig_w = orig_size
        x1, y1, x2, y2 = bbox

        # bbox 缩放到 1024 空间
        point_coords = np.array([[[x1 * scale, y1 * scale],
                                   [x2 * scale, y2 * scale]]], dtype=np.float32)
        point_labels = np.array([[2, 3]], dtype=np.float32)  # 2=box top-left, 3=box bottom-right

        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask = np.array([0], dtype=np.float32)
        orig_im_size = np.array([orig_h, orig_w], dtype=np.float32)

        outputs = self.decoder.run(None, {
            "image_embeddings": image_embeddings,
            "point_coords": point_coords,
            "point_labels": point_labels,
            "mask_input": mask_input,
            "has_mask_input": has_mask,
            "orig_im_size": orig_im_size,
        })

        # outputs[0] = masks [1, N, H, W], outputs[1] = iou, outputs[2] = low_res_masks
        masks = outputs[0]  # [1, N, H, W]
        iou_preds = outputs[1]  # [1, N]

        # 选 IoU 最高的 mask
        best_idx = np.argmax(iou_preds[0])
        mask_logits = masks[0, best_idx]  # [H, W]

        # sigmoid → binary
        mask_prob = 1.0 / (1.0 + np.exp(-np.clip(mask_logits, -50, 50)))

        # resize 回原图尺寸
        mask_resized = cv2.resize(mask_prob, (orig_w, orig_h),
                                  interpolation=cv2.INTER_LINEAR)

        # 阈值化 + 形态学清理
        binary = (mask_resized > 0.5).astype(np.uint8) * 255
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

        return binary

    def segment(self, img_bgr, bbox):
        """
        完整分割流程: 预处理 → 编码 → 解码 → mask.
        bbox: [x1, y1, x2, y2] 基于原图坐标。
        返回: binary mask (原图尺寸, uint8, 0/255)
        """
        input_hwc, scale, orig_size = self._preprocess(img_bgr)
        embeddings = self._encode(input_hwc)
        mask = self._decode(embeddings, scale, orig_size, bbox)
        return mask


# ════════════════════════════════════════════════
# Omni 视觉模型 (mimo-omni)
# ════════════════════════════════════════════════

def omni_analyze_image(image_path, prompt, max_tokens=4096):
    """调用 mimo-omni 分析图片."""
    if not os.path.exists(MIMO_API_SCRIPT):
        raise FileNotFoundError(
            f"mimo-omni 不可用: {MIMO_API_SCRIPT} 不存在\n"
            f"请确保 OpenClaw mimo-omni skill 已安装。")

    result = subprocess.run(
        ["bash", MIMO_API_SCRIPT, "image", image_path, prompt,
         "--max-tokens", str(max_tokens)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Omni 调用失败 (exit {result.returncode}): {result.stderr}")
    if not result.stdout.strip():
        raise RuntimeError("Omni 返回空结果")
    return result.stdout.strip()


def omni_verify_mask(image_path, mask_path, obj_label, scene_id):
    """
    叠层验证: Omni 审查 mask 与原图是否一致.
    返回: (passed: bool, reason: str)
    """
    img = cv2.imread(image_path)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"无法读取图片: {image_path}")
    if mask is None:
        raise RuntimeError(f"无法读取 mask: {mask_path}")

    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    # 红色半透明叠加
    overlay = img.copy()
    overlay[mask > 128] = [0, 0, 200]
    blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)

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

    if "PASS" in response.upper():
        return True, "验证通过"
    else:
        reason = response.replace("FAIL", "").strip()
        return False, reason


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
    if zone == "bottom":
        mask[h - size:h, :] = 255
    elif zone == "top":
        mask[0:size, :] = 255
    elif zone == "left":
        mask[:, 0:size] = 255
    elif zone == "right":
        mask[:, w - size:w] = 255


def process_scene(scene_id, data, sam, skip_omni_detect=False):
    """处理单个场景. 必须成功, 失败则抛异常."""
    img_path = find_scene_image(data["image"])
    if not img_path:
        raise FileNotFoundError(f"场景 {scene_id}: 图片不存在 {data['image']}")

    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError(f"场景 {scene_id}: 无法读取 {img_path}")

    h, w = img.shape[:2]
    combined = np.zeros((h, w), np.uint8)

    # ── Step 1: Omni 识别 (可选) ──
    objects = data["objects"]
    if not skip_omni_detect and objects:
        print(f"  🔍 Omni 识别物体...")
        import re
        prompt = (
            "这张图是 2D 冒险游戏的场景背景 (940x627 像素)。\n"
            "请识别所有可交互的物体/区域，返回 JSON 数组:\n"
            '[{"id": "英文标识", "label": "中文名", "bbox": [x1, y1, x2, y2]}]\n'
            "只返回 JSON, 不要其他文字。bbox 是像素坐标。"
        )
        response = omni_analyze_image(img_path, prompt)
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            detected = json.loads(json_match.group())
            print(f"  ✓ Omni 识别到 {len(detected)} 个物体")
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

        seg = sam.segment(img, bbox)
        ratio = np.count_nonzero(seg) / (h * w) * 100

        # 质量检查 (不是降级, 是精度保障)
        if ratio < 0.05:
            print(f"    ⚠️  {label}: mask 面积过小 ({ratio:.2f}%), bbox 可能不准")
        elif ratio > 35:
            print(f"    ⚠️  {label}: mask 面积过大 ({ratio:.1f}%), 尝试缩小 bbox")
            x1, y1, x2, y2 = bbox
            mx, my = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            seg = sam.segment(img, [x1 + mx, y1 + my, x2 - mx, y2 - my])

        obj_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_{obj_id}_mask.png"), obj_game)
        combined = cv2.bitwise_or(combined, seg)
        print(f"  🎯 {label} ({obj_id}): {ratio:.1f}%")

    # ── Walkable ──
    walkable_cfg = data.get("walkable")
    if walkable_cfg:
        seg = sam.segment(img, walkable_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 1.0:
            print(f"    ⚠️  walkable: mask 太小 ({ratio:.2f}%), bbox 可能不准")
        # 减去障碍物
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

    # ── Water ──
    water_cfg = data.get("water")
    if water_cfg:
        seg = sam.segment(img, water_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 0.3:
            print(f"    ⚠️  water: mask 太小 ({ratio:.2f}%), bbox 可能不准")
        seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        seg = cv2.morphologyEx(seg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        water_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_water_mask.png"), water_game)
        water_pct = np.count_nonzero(water_game) / (GAME_W * GAME_H) * 100
        print(f"  💧 water ({water_cfg['label']}): {water_pct:.1f}%")

    # ── 边缘过渡 ──
    for edge in data.get("edge_transitions", []):
        add_edge_transition(combined, edge["zone"], edge["size"], w, h)
        print(f"  🚪 边缘过渡: {edge['label']} ({edge['zone']})")

    # ── 组合 mask ──
    combined_game = cv2.resize(combined, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_mask.png"), combined_game)
    total_pct = np.count_nonzero(combined_game) / (GAME_W * GAME_H) * 100
    print(f"  💾 {scene_id}_mask.png ({total_pct:.1f}% 覆盖)")

    # ── Step 3: 叠层验证 ──
    if objects:
        print(f"  🔎 叠层验证 ({len(objects)} 个物体)...")
        for obj in objects:
            mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png")
            if os.path.exists(mask_path):
                passed, reason = omni_verify_mask(img_path, mask_path,
                                                   obj["label"], scene_id)
                status = "✅" if passed else "❌"
                print(f"    {status} {obj['label']}: {reason}")


def save_metadata():
    """保存 mask_metadata.json."""
    meta = {}
    for sid, sd in SCENES.items():
        objects = [
            {"id": o["id"], "label": o["label"],
             "mask": f"masks/{sid}_{o['id']}_mask.webp"}
            for o in sd["objects"]
        ]
        if sd.get("walkable"):
            objects.append({
                "id": "walkable", "label": sd["walkable"]["label"],
                "mask": f"masks/{sid}_walkable_mask.webp",
                "type": "walkable"
            })
        if sd.get("water"):
            objects.append({
                "id": "water", "label": sd["water"]["label"],
                "mask": f"masks/{sid}_water_mask.webp",
                "type": "water"
            })
        meta[sid] = {
            "spawn": sd.get("spawn", [0.5, 0.75]),
            "objects": objects,
            "edge_transitions": [
                {"id": e["id"], "label": e["label"],
                 "zone": e["zone"], "target": e.get("target", "")}
                for e in sd.get("edge_transitions", [])
            ]
        }
    with open(os.path.join(MASK_DIR, "mask_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def git_push_mask(scene_id, obj_id=None):
    """提交并推送."""
    msg = f"mask: {scene_id}/{obj_id}" if obj_id else f"mask: {scene_id}"
    subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)
    print(f"  📤 pushed: {msg}")


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LAST SIGNAL - MobileSAM Mask 生成器")
    parser.add_argument("--scene", help="只处理指定场景")
    parser.add_argument("--skip-omni-detect", action="store_true",
                        help="跳过 Omni 物体识别, 直接用 SCENES 中的 bbox")
    parser.add_argument("--skip-verify", action="store_true",
                        help="跳过 Omni 叠层验证")
    parser.add_argument("--no-push", action="store_true",
                        help="不自动 git push")
    args = parser.parse_args()

    print("=" * 60)
    print("🎭 LAST SIGNAL - MobileSAM + Omni Mask 生成器")
    print("=" * 60)

    # ── 加载 MobileSAM (必须成功) ──
    print("\n🔧 加载模型...")
    sam = MobileSAM()

    # ── 检查 Omni ──
    if not os.path.exists(MIMO_API_SCRIPT):
        raise FileNotFoundError(
            f"mimo-omni 不可用: {MIMO_API_SCRIPT}\n"
            f"请确保 OpenClaw mimo-omni skill 已安装。")
    print(f"  ✓ Omni: {MIMO_API_SCRIPT}")

    # ── 处理场景 ──
    scenes_to_process = SCENES
    if args.scene:
        if args.scene not in SCENES:
            print(f"❌ 未知场景: {args.scene}")
            print(f"   可用: {', '.join(SCENES.keys())}")
            sys.exit(1)
        scenes_to_process = {args.scene: SCENES[args.scene]}

    for scene_id, data in scenes_to_process.items():
        print(f"\n{'─' * 50}")
        print(f"🎬 {scene_id}")
        print(f"{'─' * 50}")

        process_scene(scene_id, data, sam,
                       skip_omni_detect=args.skip_omni_detect)

        if not args.no_push:
            git_push_mask(scene_id)

    # ── 元数据 ──
    save_metadata()
    if not args.no_push:
        git_push_mask("_metadata")

    total_obj = sum(len(s["objects"]) for s in SCENES.values())
    total_edge = sum(len(s.get("edge_transitions", [])) for s in SCENES.values())
    print(f"\n{'=' * 60}")
    print(f"✅ 完成: {total_obj} 个物体 + {total_edge} 个边缘过渡")
    print(f"📁 {MASK_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
