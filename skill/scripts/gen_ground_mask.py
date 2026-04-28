#!/usr/bin/env python3
"""
LAST SIGNAL - 迭代式地面 Mask 生成器

流程:
  1. Omni 视觉模型识别场景中的地面区域 → 多个小矩形框
  2. MobileSAM v2 基于每个小框生成精确 mask
  3. 逐个叠层到合成 mask 上
  4. Omni 审查叠层结果，判断是否符合预期
  5. 迭代 2-3 轮，直到地面 mask 完整

目标: 精确识别地面/路面区域，用于 walkable mask 生成。

依赖: onnxruntime, pillow, numpy, opencv-python-headless
模型: models/mobilesam_v2.encoder.onnx + models/mobilesam_v2.decoder.onnx
"""

import cv2
import numpy as np
import json
import os
import sys
import subprocess
import re
import time
from pathlib import Path
from datetime import datetime

from PIL import Image
import onnxruntime as ort

# ── 常量 ──
IMG_W, IMG_H = 940, 627
GAME_W, GAME_H = 960, 640
MOBILESAM_SIZE = 1024

# ImageNet 归一化参数
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
MASK_DIR = os.path.join(ASSETS_DIR, "masks")
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
LOG_DIR = os.path.join(PROJECT_DIR, "ground_detection_logs")

os.makedirs(MASK_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ── Omni API ──
MIMO_API_SCRIPT = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")

# ── MobileSAM v2 模型路径 ──
ENCODER_PATH = os.path.join(MODELS_DIR, "mobilesam_v2.encoder.onnx")
DECODER_PATH = os.path.join(MODELS_DIR, "mobilesam_v2.decoder.onnx")

# 回退到 v1 模型
ENCODER_PATH_V1 = os.path.join(MODELS_DIR, "mobilesam.encoder.onnx")
DECODER_PATH_V1 = os.path.join(MODELS_DIR, "mobile_sam.onnx")


# ════════════════════════════════════════════════
# 日志系统
# ════════════════════════════════════════════════

class DetectionLog:
    """记录所有中间状态和思维过程."""

    def __init__(self, scene_id):
        self.scene_id = scene_id
        self.start_time = datetime.now()
        self.rounds = []
        self.current_round = None
        self.final_result = None

    def start_round(self, round_num, description):
        self.current_round = {
            "round": round_num,
            "description": description,
            "start_time": datetime.now().isoformat(),
            "steps": [],
            "omni_proposals": [],
            "sam_results": [],
            "overlay_reviews": [],
            "end_time": None,
        }

    def log_step(self, step_type, content, image_path=None):
        if self.current_round:
            self.current_round["steps"].append({
                "type": step_type,
                "content": content,
                "image_path": image_path,
                "timestamp": datetime.now().isoformat(),
            })

    def log_omni_proposal(self, boxes):
        if self.current_round:
            self.current_round["omni_proposals"].append({
                "boxes": boxes,
                "count": len(boxes),
                "timestamp": datetime.now().isoformat(),
            })

    def log_sam_result(self, box_id, bbox, mask_area_pct, mask_path):
        if self.current_round:
            self.current_round["sam_results"].append({
                "box_id": box_id,
                "bbox": bbox,
                "area_pct": mask_area_pct,
                "mask_path": mask_path,
                "timestamp": datetime.now().isoformat(),
            })

    def log_overlay_review(self, review_text, passed, overlay_path):
        if self.current_round:
            self.current_round["overlay_reviews"].append({
                "review": review_text,
                "passed": passed,
                "overlay_path": overlay_path,
                "timestamp": datetime.now().isoformat(),
            })

    def end_round(self):
        if self.current_round:
            self.current_round["end_time"] = datetime.now().isoformat()
            self.rounds.append(self.current_round)
            self.current_round = None

    def set_final_result(self, mask_path, coverage_pct):
        self.final_result = {
            "mask_path": mask_path,
            "coverage_pct": coverage_pct,
            "total_rounds": len(self.rounds),
            "total_time": str(datetime.now() - self.start_time),
        }

    def save(self):
        log_data = {
            "scene_id": self.scene_id,
            "start_time": self.start_time.isoformat(),
            "rounds": self.rounds,
            "final_result": self.final_result,
        }
        log_path = os.path.join(LOG_DIR, f"{self.scene_id}_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)
        return log_path


# ════════════════════════════════════════════════
# MobileSAM ONNX (支持 v1 和 v2)
# ════════════════════════════════════════════════

class MobileSAM:
    """MobileSAM ONNX 推理器: encoder + decoder, 支持 v1/v2."""

    def __init__(self, use_v2=True):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2

        if use_v2 and os.path.isfile(ENCODER_PATH) and os.path.isfile(DECODER_PATH):
            enc_path, dec_path = ENCODER_PATH, DECODER_PATH
            version = "v2"
        elif os.path.isfile(ENCODER_PATH_V1) and os.path.isfile(DECODER_PATH_V1):
            enc_path, dec_path = ENCODER_PATH_V1, DECODER_PATH_V1
            version = "v1"
            if use_v2:
                print("  ⚠️  MobileSAM v2 模型不存在，回退到 v1")
        else:
            raise FileNotFoundError(
                f"MobileSAM 模型不存在。\n"
                f"请运行: bash setup.sh 或手动下载:\n"
                f"  v1: models/mobilesam.encoder.onnx + models/mobile_sam.onnx\n"
                f"  v2: models/mobilesam_v2.encoder.onnx + models/mobilesam_v2.decoder.onnx")

        print(f"  📦 加载 encoder ({version}): {enc_path}")
        self.encoder = ort.InferenceSession(enc_path, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  📦 加载 decoder ({version}): {dec_path}")
        self.decoder = ort.InferenceSession(dec_path, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  ✓ MobileSAM {version} 就绪")

    def _preprocess(self, img_bgr):
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]
        scale = MOBILESAM_SIZE / max(orig_h, orig_w)
        new_h, new_w = int(orig_h * scale), int(orig_w * scale)
        resized = cv2.resize(img_rgb, (new_w, new_h),
                             interpolation=cv2.INTER_LINEAR)
        padded = np.zeros((MOBILESAM_SIZE, MOBILESAM_SIZE, 3), dtype=np.uint8)
        padded[:new_h, :new_w, :] = resized
        normalized = (padded.astype(np.float32) / 255.0 - MEAN) / STD
        return normalized, scale, (orig_h, orig_w)

    def _encode(self, input_hwc):
        return self.encoder.run(None, {"input_image": input_hwc})[0]

    def _decode(self, image_embeddings, scale, orig_size, bbox):
        orig_h, orig_w = orig_size
        x1, y1, x2, y2 = bbox
        point_coords = np.array([[[x1 * scale, y1 * scale],
                                   [x2 * scale, y2 * scale]]], dtype=np.float32)
        point_labels = np.array([[2, 3]], dtype=np.float32)
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

        masks = outputs[0]
        iou_preds = outputs[1]
        best_idx = np.argmax(iou_preds[0])
        mask_logits = masks[0, best_idx]
        mask_prob = 1.0 / (1.0 + np.exp(-np.clip(mask_logits, -50, 50)))
        mask_resized = cv2.resize(mask_prob, (orig_w, orig_h),
                                  interpolation=cv2.INTER_LINEAR)
        binary = (mask_resized > 0.5).astype(np.uint8) * 255
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
        return binary

    def segment(self, img_bgr, bbox):
        input_hwc, scale, orig_size = self._preprocess(img_bgr)
        embeddings = self._encode(input_hwc)
        mask = self._decode(embeddings, scale, orig_size, bbox)
        return mask

    def segment_with_embeddings(self, img_bgr, bboxes):
        """一次编码，多次解码（共享 embeddings，效率更高）."""
        input_hwc, scale, orig_size = self._preprocess(img_bgr)
        embeddings = self._encode(input_hwc)
        masks = []
        for bbox in bboxes:
            mask = self._decode(embeddings, scale, orig_size, bbox)
            masks.append(mask)
        return masks


# ════════════════════════════════════════════════
# Omni 视觉模型
# ════════════════════════════════════════════════

def omni_analyze_image(image_path, prompt, max_tokens=4096):
    if not os.path.exists(MIMO_API_SCRIPT):
        raise FileNotFoundError(f"mimo-omni 不可用: {MIMO_API_SCRIPT}")
    result = subprocess.run(
        ["bash", MIMO_API_SCRIPT, "image", image_path, prompt,
         "--max-tokens", str(max_tokens)],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"Omni 调用失败: {result.stderr}")
    if not result.stdout.strip():
        print("  ⚠️  Omni 返回空结果，重试一次...")
        result = subprocess.run(
            ["bash", MIMO_API_SCRIPT, "image", image_path, prompt,
             "--max-tokens", str(max_tokens)],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("Omni 返回空结果（重试后仍失败）")
    return result.stdout.strip()


def omni_identify_ground_patches(image_path, scene_id, round_num=1, previous_masks=None):
    """
    Omni 识别地面区域，返回多个小矩形框。

    策略: 每次只识别几个小的地面 patch，而不是一大片。
    这样 SAM 可以更精确地分割每个小区域。
    """
    context = ""
    if previous_masks and round_num > 1:
        context = (
            f"\n\n这是第 {round_num} 轮。前一轮已识别的地面区域用红色标记。\n"
            "请识别尚未覆盖的地面区域，或者前一轮识别不准确的区域。\n"
            "重点关注：路面、地板、地面材质连续的区域。"
        )

    prompt = (
        f"这张图是 2D 冒险游戏 '{scene_id}' 的场景背景 (940x627 像素)。\n"
        f"你的任务是识别图中的【地面/路面】区域。\n\n"
        f"要求:\n"
        f"1. 返回 8-15 个**很小的**矩形框，每个框只覆盖一小块地面区域\n"
        f"2. 每个框的宽度和高度都不要超过 80 像素（大约 80x80 以内）\n"
        f"3. **重要：框要分散在整个地面区域，不要只集中在某一处**。从近景到远景都要覆盖\n"
        f"4. 框要精确覆盖地面，不要包含墙壁、天花板、物体\n"
        f"5. 优先识别：人行道、路面、地板、台阶等可行走表面\n"
        f"6. 避开：墙壁、窗户、门、家具、人物、杂物\n"
        f"7. 框的坐标是像素坐标 [x1, y1, x2, y2]，确保 x2-x1 <= 80 且 y2-y1 <= 80\n\n"
        f"返回 JSON 数组:\n"
        f'[{{"id": "patch_1", "label": "地面描述", "bbox": [x1, y1, x2, y2]}}]\n'
        f"只返回 JSON，不要其他文字。"
        f"{context}"
    )

    if previous_masks:
        # 创建带标记的预览图
        img = cv2.imread(image_path)
        overlay = img.copy()
        for mask_path in previous_masks:
            if os.path.exists(mask_path):
                m = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if m is not None and m.shape[:2] == img.shape[:2]:
                    overlay[m > 128] = [0, 0, 200]  # 红色标记已识别区域
        blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)
        preview_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_context.png")
        cv2.imwrite(preview_path, blended)
        try:
            response = omni_analyze_image(preview_path, prompt)
        except RuntimeError as e:
            print(f"  ⚠️  Omni 调用失败: {e}")
            return []
    else:
        try:
            response = omni_analyze_image(image_path, prompt)
        except RuntimeError as e:
            print(f"  ⚠️  Omni 调用失败: {e}")
            return []

    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if not json_match:
        print(f"  ⚠️  Omni 未返回有效 JSON，使用默认地面框")
        return []

    try:
        boxes = json.loads(json_match.group())
        # Clip oversized boxes to max 80px per dimension
        MAX_PATCH_SIZE = 80
        for box in boxes:
            bbox = box.get("bbox", [])
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                w, h = x2 - x1, y2 - y1
                if w > MAX_PATCH_SIZE or h > MAX_PATCH_SIZE:
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    new_w = min(w, MAX_PATCH_SIZE)
                    new_h = min(h, MAX_PATCH_SIZE)
                    box["bbox"] = [cx - new_w // 2, cy - new_h // 2,
                                   cx + new_w // 2, cy + new_h // 2]
        return boxes
    except json.JSONDecodeError:
        print(f"  ⚠️  JSON 解析失败")
        return []


def omni_review_ground_overlay(image_path, mask_path, scene_id, round_num):
    """
    Omni 审查地面 mask 叠层结果。

    返回: (passed: bool, feedback: str, suggested_fixes: list)
    """
    img = cv2.imread(image_path)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if img is None or mask is None:
        return False, "无法读取图片或 mask", []

    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    # 绿色半透明叠加表示地面区域
    overlay = img.copy()
    overlay[mask > 128] = [0, 200, 0]  # 绿色
    blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)

    preview_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_review.png")
    cv2.imwrite(preview_path, blended)

    prompt = (
        f"这是游戏场景 '{scene_id}' 第 {round_num} 轮地面识别结果。\n"
        f"绿色半透明区域是识别出的地面/可行走区域。\n\n"
        f"请判断:\n"
        f"1. 绿色区域是否准确覆盖了地面？（是/否）\n"
        f"2. 是否有绿色区域覆盖到了非地面物体（墙壁、家具等）？（是/否）\n"
        f"3. 是否有明显的地面区域未被覆盖？（是/否）\n"
        f"4. 整体覆盖率是否足够？（是/否）\n\n"
        f"如果地面识别质量合格，回复: PASS\n"
        f"如果需要改进，回复: FAIL <具体问题>\n"
        f"如果有遗漏区域，追加: MISSING [x1,y1,x2,y2] <描述>\n"
        f"如果有误覆盖区域，追加: OVERCOVER [x1,y1,x2,y2] <描述>\n"
    )

    try:
        response = omni_analyze_image(preview_path, prompt)
    except RuntimeError as e:
        print(f"  ⚠️  Omni 审查失败: {e}")
        return False, str(e), []

    passed = "PASS" in response.upper() and "FAIL" not in response.upper()

    # 解析 MISSING 和 OVERCOVER 建议
    suggested_fixes = []
    for match in re.finditer(r'MISSING\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]\s*(.*)', response):
        suggested_fixes.append({
            "type": "missing",
            "bbox": [int(match.group(1)), int(match.group(2)),
                     int(match.group(3)), int(match.group(4))],
            "description": match.group(5).strip()
        })
    for match in re.finditer(r'OVERCOVER\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]\s*(.*)', response):
        suggested_fixes.append({
            "type": "overcover",
            "bbox": [int(match.group(1)), int(match.group(2)),
                     int(match.group(3)), int(match.group(4))],
            "description": match.group(5).strip()
        })

    return passed, response, suggested_fixes


# ════════════════════════════════════════════════
# 迭代式地面检测
# ════════════════════════════════════════════════

def find_scene_image(image_name):
    base = os.path.splitext(image_name)[0]
    for ext in [".webp", ".png"]:
        path = os.path.join(ASSETS_DIR, base + ext)
        if os.path.exists(path):
            return path
    return None


def create_overlay_preview(img, mask, color=(0, 200, 0), alpha=0.4):
    overlay = img.copy()
    overlay[mask > 128] = color
    return cv2.addWeighted(img, 1 - alpha, overlay, alpha, 0)


def iterative_ground_detection(scene_id, scene_data, sam, max_rounds=3):
    """
    迭代式地面检测主流程。

    每轮:
    1. Omni 识别多个小地面 patch
    2. SAM 对每个 patch 生成 mask
    3. 叠层到合成 mask
    4. Omni 审查，决定是否需要下一轮
    """
    log = DetectionLog(scene_id)

    img_path = find_scene_image(scene_data["image"])
    if not img_path:
        raise FileNotFoundError(f"场景 {scene_id}: 图片不存在")

    img = cv2.imread(img_path)
    h, w = img.shape[:2]

    # 最终合成 mask
    ground_mask = np.zeros((h, w), np.uint8)
    all_patches = []  # 记录所有 patch

    print(f"\n{'═' * 60}")
    print(f"🌍 场景: {scene_id}")
    print(f"   图片: {img_path} ({w}x{h})")
    print(f"   最大轮次: {max_rounds}")
    print(f"{'═' * 60}")

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─' * 50}")
        print(f"📍 第 {round_num} 轮")
        print(f"{'─' * 50}")

        log.start_round(round_num, f"第 {round_num} 轮地面识别")

        # ── Step 1: Omni 识别地面 patch ──
        print(f"  🔍 Omni 识别地面 patch...")
        previous_mask_paths = []
        if round_num > 1:
            # 保存当前 ground mask 供 Omni 参考
            prev_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num-1}_ground.png")
            cv2.imwrite(prev_path, ground_mask)
            previous_mask_paths.append(prev_path)

        patches = omni_identify_ground_patches(
            img_path, scene_id, round_num, previous_mask_paths)

        if not patches:
            print(f"  ⚠️  Omni 未识别到新 patch，结束迭代")
            log.log_step("warning", "Omni 未识别到新 patch")
            log.end_round()
            break

        log.log_omni_proposal(patches)
        print(f"  ✓ 识别到 {len(patches)} 个 patch:")
        for p in patches:
            print(f"    - {p.get('id', '?')}: {p.get('label', '?')} {p.get('bbox', [])}")

        # ── Step 2: SAM 对每个 patch 生成 mask ──
        print(f"  🎯 SAM 分割...")
        patch_masks = []
        for i, patch in enumerate(patches):
            bbox = patch.get("bbox", [])
            if len(bbox) != 4:
                print(f"    ⚠️  patch {i}: bbox 无效，跳过")
                continue

            # 确保 bbox 在图片范围内
            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 < 10 or y2 - y1 < 10:
                print(f"    ⚠️  patch {i}: bbox 太小，跳过")
                continue

            mask = sam.segment(img, [x1, y1, x2, y2])
            area_pct = np.count_nonzero(mask) / (h * w) * 100

            # 保存单个 patch mask
            patch_mask_path = os.path.join(
                LOG_DIR, f"{scene_id}_r{round_num}_patch{i}_mask.png")
            cv2.imwrite(patch_mask_path, mask)

            patch_masks.append(mask)
            all_patches.append({
                "round": round_num,
                "patch_id": patch.get("id", f"patch_{i}"),
                "bbox": [x1, y1, x2, y2],
                "area_pct": area_pct,
            })

            log.log_sam_result(
                patch.get("id", f"patch_{i}"),
                [x1, y1, x2, y2],
                area_pct,
                patch_mask_path
            )

            print(f"    ✓ {patch.get('id', '?')}: {area_pct:.1f}% 覆盖")

        if not patch_masks:
            print(f"  ⚠️  无有效 patch mask")
            log.log_step("warning", "无有效 patch mask")
            log.end_round()
            continue

        # ── Step 3: 叠层到合成 mask ──
        print(f"  📊 叠层合成...")
        for mask in patch_masks:
            ground_mask = cv2.bitwise_or(ground_mask, mask)

        # 形态学清理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_CLOSE, kernel)
        ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_OPEN, kernel)

        total_pct = np.count_nonzero(ground_mask) / (h * w) * 100
        print(f"  📈 累计地面覆盖: {total_pct:.1f}%")

        # 保存本轮 ground mask
        round_mask_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_ground.png")
        cv2.imwrite(round_mask_path, ground_mask)

        # 保存叠层预览
        preview = create_overlay_preview(img, ground_mask, (0, 200, 0))
        preview_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_preview.png")
        cv2.imwrite(preview_path, preview)

        log.log_step("overlay", f"累计覆盖 {total_pct:.1f}%", round_mask_path)

        # ── Step 4: Omni 审查 ──
        print(f"  🔎 Omni 审查...")
        passed, review, fixes = omni_review_ground_overlay(
            img_path, round_mask_path, scene_id, round_num)

        log.log_overlay_review(review, passed, preview_path)

        if passed:
            print(f"  ✅ 审查通过!")
            log.log_step("review", f"PASS: {review}")
            log.end_round()
            break
        else:
            print(f"  ❌ 需要改进: {review[:100]}...")
            if fixes:
                print(f"  📝 {len(fixes)} 个修正建议:")
                for fix in fixes:
                    print(f"    - {fix['type']}: {fix['bbox']} ({fix['description']})")
            log.log_step("review", f"FAIL: {review}")

            # 如果有 OVERCOVER 建议，从 ground_mask 中移除
            for fix in fixes:
                if fix["type"] == "overcover":
                    x1, y1, x2, y2 = fix["bbox"]
                    ground_mask[y1:y2, x1:x2] = 0
                    print(f"    ✂️  移除误覆盖区域: {fix['bbox']}")

            log.end_round()

    # ── 最终处理 ──
    # 减去障碍物区域
    for obj in scene_data.get("objects", []):
        obj_mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png")
        if os.path.exists(obj_mask_path):
            obs = cv2.imread(obj_mask_path, cv2.IMREAD_GRAYSCALE)
            if obs is not None:
                obs = cv2.resize(obs, (w, h), interpolation=cv2.INTER_NEAREST)
                ground_mask[obs > 128] = 0
                print(f"  ✂️  减去障碍物: {obj['label']}")

    # 最终形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_CLOSE, kernel)
    ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_OPEN, kernel)

    # 保存最终 mask
    final_game = cv2.resize(ground_mask, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
    final_path = os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.png")
    cv2.imwrite(final_path, final_game)

    final_pct = np.count_nonzero(final_game) / (GAME_W * GAME_H) * 100
    print(f"\n  💾 最终 walkable mask: {final_path}")
    print(f"  📊 覆盖率: {final_pct:.1f}%")

    # 保存最终预览
    final_preview = create_overlay_preview(img, ground_mask, (0, 200, 0))
    final_preview_path = os.path.join(LOG_DIR, f"{scene_id}_final_preview.png")
    cv2.imwrite(final_preview_path, final_preview)

    log.set_final_result(final_path, final_pct)
    log_path = log.save()
    print(f"  📝 日志: {log_path}")

    return ground_mask, log


# ════════════════════════════════════════════════
# 场景定义
# ════════════════════════════════════════════════

TARGET_SCENES = {
    "apartment": {
        "image": "bg_apartment.png",
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
    "alley": {
        "image": "bg_alley.png",
        "objects": [
            {"id": "shadow", "label": "影子 (数据贩子)", "bbox": [230, 120, 520, 480]},
            {"id": "graffiti", "label": "涂鸦墙", "bbox": [10, 200, 230, 560]},
            {"id": "exit", "label": "返回街道", "bbox": [740, 300, 938, 627]},
        ],
        "walkable": {"bbox": [60, 120, 900, 627], "label": "巷子地面"},
        "water": {"bbox": [60, 460, 900, 627], "label": "巷子积水"},
        "edge_transitions": []
    },
}


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LAST SIGNAL - 迭代式地面 Mask 生成器")
    parser.add_argument("--scene", choices=["apartment", "alley"],
                        help="只处理指定场景")
    parser.add_argument("--max-rounds", type=int, default=3,
                        help="最大迭代轮次 (默认 3)")
    parser.add_argument("--use-v1", action="store_true",
                        help="强制使用 MobileSAM v1")
    parser.add_argument("--no-push", action="store_true",
                        help="不自动 git push")
    args = parser.parse_args()

    print("=" * 60)
    print("🌍 LAST SIGNAL - 迭代式地面 Mask 生成器")
    print("=" * 60)

    # ── 加载模型 ──
    print("\n🔧 加载模型...")
    sam = MobileSAM(use_v2=not args.use_v1)

    # ── 检查 Omni ──
    if not os.path.exists(MIMO_API_SCRIPT):
        raise FileNotFoundError(f"mimo-omni 不可用: {MIMO_API_SCRIPT}")
    print(f"  ✓ Omni: {MIMO_API_SCRIPT}")

    # ── 处理场景 ──
    scenes = TARGET_SCENES
    if args.scene:
        scenes = {args.scene: TARGET_SCENES[args.scene]}

    results = {}
    for scene_id, data in scenes.items():
        ground_mask, log = iterative_ground_detection(
            scene_id, data, sam, max_rounds=args.max_rounds)
        results[scene_id] = {
            "mask": ground_mask,
            "log": log,
        }

        if not args.no_push:
            subprocess.run(["git", "add", "-A"], cwd=PROJECT_DIR, check=True)
            subprocess.run(["git", "commit", "-m", f"mask: regenerate {scene_id} walkable (iterative ground detection)"],
                          cwd=PROJECT_DIR, check=True)
            subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True)
            print(f"  📤 pushed: {scene_id}")

    # ── 汇总 ──
    print(f"\n{'=' * 60}")
    print(f"✅ 完成! 处理了 {len(results)} 个场景")
    for sid, r in results.items():
        final = r["log"].final_result
        if final:
            print(f"  {sid}: {final['coverage_pct']:.1f}% 覆盖, {final['total_rounds']} 轮")
    print(f"📁 日志目录: {LOG_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
