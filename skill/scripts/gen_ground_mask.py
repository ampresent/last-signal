#!/usr/bin/env python3
"""
LAST SIGNAL - 迭代式地面 Mask 生成器 (v2)

流程:
  1. Omni 识别 4 个小地面 patch (≤50px)
  2. MobileSAM 对每个 patch 生成 mask
  3. 逐个叠层到合成 mask，每个 patch 带编号标注
  4. Omni 逐块审查：每块单独判断 PASS/FAIL
  5. FAIL 的删掉，PASS 的保留
  6. 下一轮补充 4 个新 patch，重复 2-3 轮

目标: 精确识别地面/路面区域，用于 walkable mask 生成。

依赖: onnxruntime, pillow, numpy, opencv-python-headless
模型: models/mobilesam.encoder.onnx + models/mobile_sam.onnx
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
MAX_PATCH_SIZE = 50  # 每个 patch 最大 50px

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

# ── MobileSAM 模型路径 ──
ENCODER_PATH = os.path.join(MODELS_DIR, "mobilesam.encoder.onnx")
DECODER_PATH = os.path.join(MODELS_DIR, "mobile_sam.onnx")


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
            "patch_reviews": [],  # 逐块审查结果
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

    def log_sam_result(self, patch_id, bbox, mask_area_pct, mask_path):
        if self.current_round:
            self.current_round["sam_results"].append({
                "patch_id": patch_id,
                "bbox": bbox,
                "area_pct": mask_area_pct,
                "mask_path": mask_path,
                "timestamp": datetime.now().isoformat(),
            })

    def log_patch_review(self, patch_id, passed, review_text, overlay_path):
        if self.current_round:
            self.current_round["patch_reviews"].append({
                "patch_id": patch_id,
                "passed": passed,
                "review": review_text,
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
# MobileSAM ONNX
# ════════════════════════════════════════════════

class MobileSAM:
    """MobileSAM ONNX 推理器: encoder + decoder."""

    def __init__(self):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 2

        if not os.path.isfile(ENCODER_PATH):
            raise FileNotFoundError(f"MobileSAM encoder 不存在: {ENCODER_PATH}")
        if not os.path.isfile(DECODER_PATH):
            raise FileNotFoundError(f"MobileSAM decoder 不存在: {DECODER_PATH}")

        print(f"  📦 加载 encoder: {ENCODER_PATH}")
        self.encoder = ort.InferenceSession(ENCODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  📦 加载 decoder: {DECODER_PATH}")
        self.decoder = ort.InferenceSession(DECODER_PATH, opts,
                                            providers=["CPUExecutionProvider"])
        print(f"  ✓ MobileSAM 就绪")

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
        # 重试一次
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
    Omni 识别 4 个小地面 patch。
    """
    context = ""
    if previous_masks and round_num > 1:
        context = (
            f"\n\n这是第 {round_num} 轮。前一轮已识别并验证通过的地面区域用红色标记。\n"
            "请识别尚未覆盖的地面区域。选择与已有区域不重叠的位置。"
        )

    prompt = (
        f"这张图是 2D 冒险游戏 '{scene_id}' 的场景背景 (940x627 像素)。\n"
        f"你的任务是识别图中的【地面/路面】区域。\n\n"
        f"要求:\n"
        f"1. 恰好返回 4 个小矩形框\n"
        f"2. 每个框的宽度和高度都不要超过 50 像素\n"
        f"3. 框要分散在不同位置，不要挤在一起\n"
        f"4. 只框选确定是地面的区域（地板、路面、人行道）\n"
        f"5. 不要框选：墙壁、天花板、家具、人物、杂物\n"
        f"6. 坐标是像素坐标 [x1, y1, x2, y2]\n\n"
        f"返回 JSON 数组:\n"
        f'[{{"id": "p1", "bbox": [x1, y1, x2, y2]}}, ...]\n'
        f"只返回 JSON，不要其他文字。"
        f"{context}"
    )

    if previous_masks:
        img = cv2.imread(image_path)
        overlay = img.copy()
        for mask_path in previous_masks:
            if os.path.exists(mask_path):
                m = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if m is not None and m.shape[:2] == img.shape[:2]:
                    overlay[m > 128] = [0, 0, 200]
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
        print(f"  ⚠️  Omni 未返回有效 JSON")
        return []

    try:
        boxes = json.loads(json_match.group())
        # 强制裁剪到 MAX_PATCH_SIZE
        for box in boxes:
            bbox = box.get("bbox", [])
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                w, h = x2 - x1, y2 - y1
                if w > MAX_PATCH_SIZE or h > MAX_PATCH_SIZE:
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    hw = min(w, MAX_PATCH_SIZE) // 2
                    hh = min(h, MAX_PATCH_SIZE) // 2
                    box["bbox"] = [cx - hw, cy - hh, cx + hw, cy + hh]
        return boxes[:4]  # 最多 4 个
    except json.JSONDecodeError:
        print(f"  ⚠️  JSON 解析失败")
        return []


def omni_review_single_patch(image_path, patch_overlay_path, scene_id,
                              round_num, patch_id, patch_label):
    """
    Omni 审查单个 patch 的叠层结果。

    返回: (passed: bool, review: str)
    """
    prompt = (
        f"这是游戏场景 '{scene_id}' 的地面检测结果。\n"
        f"图中标注了 patch '{patch_id}'（{patch_label}）的检测区域。\n"
        f"红色数字标签标识每个 patch 的位置。\n\n"
        f"请判断 patch '{patch_id}' 是否准确：\n"
        f"1. 该 patch 是否覆盖了地面/路面？（是/否）\n"
        f"2. 该 patch 是否误覆盖了非地面物体（墙壁、家具等）？（是/否）\n\n"
        f"如果该 patch 是准确的地面区域，回复: PASS\n"
        f"如果不准确（覆盖了非地面），回复: FAIL <原因>\n"
        f"只回复 PASS 或 FAIL，不要其他文字。"
    )

    try:
        response = omni_analyze_image(patch_overlay_path, prompt)
    except RuntimeError as e:
        print(f"    ⚠️  Omni 审查 {patch_id} 失败: {e}")
        return False, str(e)

    passed = "PASS" in response.upper() and "FAIL" not in response.upper()
    return passed, response


def create_patch_review_image(img, ground_mask, current_patch_mask, patch_id,
                               patch_idx, bbox, all_accepted_masks=None):
    """
    创建带编号标注的叠层预览图。

    - 绿色半透明: 已接受的地面区域
    - 当前 patch 用不同颜色高亮
    - 红色数字标签标注 patch 编号
    """
    h, w = img.shape[:2]
    result = img.copy()

    # 已接受的区域用绿色
    if all_accepted_masks is not None:
        result[all_accepted_masks > 128] = (
            result[all_accepted_masks > 128].astype(np.float32) * 0.6 +
            np.array([0, 200, 0], dtype=np.float32) * 0.4
        ).astype(np.uint8)

    # 当前 patch 用黄色高亮
    if current_patch_mask is not None:
        result[current_patch_mask > 128] = (
            result[current_patch_mask > 128].astype(np.float32) * 0.5 +
            np.array([0, 220, 255], dtype=np.float32) * 0.5
        ).astype(np.uint8)

    # 在 patch 中心画编号
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    label = f"#{patch_id}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2
    (tw, th), _ = cv2.getTextSize(label, font, font_scale, thickness)
    # 白底黑字
    cv2.rectangle(result, (cx - tw // 2 - 4, cy - th - 4),
                  (cx + tw // 2 + 4, cy + 4), (255, 255, 255), -1)
    cv2.putText(result, label, (cx - tw // 2, cy), font, font_scale,
                (0, 0, 200), thickness)

    return result


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


def iterative_ground_detection(scene_id, scene_data, sam, max_rounds=3):
    """
    迭代式地面检测主流程 (v2: 逐块审查)。

    每轮:
    1. Omni 识别 4 个小 patch
    2. SAM 对每个 patch 生成 mask
    3. 逐个叠层到合成 mask，带编号标注
    4. Omni 逐块审查: PASS/FAIL
    5. FAIL 的删除，PASS 的保留
    """
    log = DetectionLog(scene_id)

    img_path = find_scene_image(scene_data["image"])
    if not img_path:
        raise FileNotFoundError(f"场景 {scene_id}: 图片不存在")

    img = cv2.imread(img_path)
    h, w = img.shape[:2]

    # 最终合成 mask（只包含 PASS 的 patch）
    ground_mask = np.zeros((h, w), np.uint8)
    all_patches = []  # 记录所有 patch 信息

    print(f"\n{'═' * 60}")
    print(f"🌍 场景: {scene_id}")
    print(f"   图片: {img_path} ({w}x{h})")
    print(f"   最大轮次: {max_rounds}")
    print(f"   Patch 大小: ≤{MAX_PATCH_SIZE}px")
    print(f"   每轮 Patch 数: 4")
    print(f"{'═' * 60}")

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─' * 50}")
        print(f"📍 第 {round_num} 轮")
        print(f"{'─' * 50}")

        log.start_round(round_num, f"第 {round_num} 轮地面识别")

        # ── Step 1: Omni 识别 4 个 patch ──
        print(f"  🔍 Omni 识别 4 个地面 patch...")
        previous_mask_paths = []
        if round_num > 1:
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
            print(f"    - {p.get('id', '?')}: {p.get('bbox', [])}")

        # ── Step 2: SAM 分割 + Step 3: 逐块审查 ──
        print(f"  🎯 SAM 分割 + 逐块审查...")
        accepted_count = 0
        rejected_count = 0

        for i, patch in enumerate(patches):
            bbox = patch.get("bbox", [])
            patch_id = patch.get("id", f"p{i+1}")

            if len(bbox) != 4:
                print(f"    ⚠️  {patch_id}: bbox 无效，跳过")
                continue

            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 < 10 or y2 - y1 < 10:
                print(f"    ⚠️  {patch_id}: bbox 太小，跳过")
                continue

            # SAM 分割
            mask = sam.segment(img, [x1, y1, x2, y2])
            area_pct = np.count_nonzero(mask) / (h * w) * 100

            # 保存单个 patch mask
            patch_mask_path = os.path.join(
                LOG_DIR, f"{scene_id}_r{round_num}_{patch_id}_mask.png")
            cv2.imwrite(patch_mask_path, mask)

            log.log_sam_result(patch_id, [x1, y1, x2, y2], area_pct, patch_mask_path)
            print(f"    🎯 {patch_id}: {area_pct:.1f}% 覆盖 (SAM)")

            # 创建带编号的叠层预览图
            review_img = create_patch_review_image(
                img, ground_mask, mask, patch_id, i, [x1, y1, x2, y2],
                all_accepted_masks=ground_mask)
            review_path = os.path.join(
                LOG_DIR, f"{scene_id}_r{round_num}_{patch_id}_review.png")
            cv2.imwrite(review_path, review_img)

            # Omni 逐块审查
            passed, review_text = omni_review_single_patch(
                img_path, review_path, scene_id, round_num, patch_id,
                f"地面区域 {patch_id}")

            log.log_patch_review(patch_id, passed, review_text, review_path)

            if passed:
                # 接受：叠层到 ground_mask
                ground_mask = cv2.bitwise_or(ground_mask, mask)
                accepted_count += 1
                all_patches.append({
                    "round": round_num,
                    "patch_id": patch_id,
                    "bbox": [x1, y1, x2, y2],
                    "area_pct": area_pct,
                    "verdict": "PASS",
                })
                print(f"    ✅ {patch_id}: PASS — 已叠层")
            else:
                rejected_count += 1
                all_patches.append({
                    "round": round_num,
                    "patch_id": patch_id,
                    "bbox": [x1, y1, x2, y2],
                    "area_pct": area_pct,
                    "verdict": "FAIL",
                    "reason": review_text[:200],
                })
                print(f"    ❌ {patch_id}: FAIL — 已删除 ({review_text[:60]}...)")

        # 形态学清理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_CLOSE, kernel)
        ground_mask = cv2.morphologyEx(ground_mask, cv2.MORPH_OPEN, kernel)

        total_pct = np.count_nonzero(ground_mask) / (h * w) * 100
        print(f"\n  📊 本轮结果: {accepted_count} PASS, {rejected_count} FAIL")
        print(f"  📈 累计地面覆盖: {total_pct:.1f}%")

        # 保存本轮 ground mask
        round_mask_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_ground.png")
        cv2.imwrite(round_mask_path, ground_mask)

        # 保存叠层预览
        preview = img.copy()
        preview[ground_mask > 128] = (
            preview[ground_mask > 128].astype(np.float32) * 0.6 +
            np.array([0, 200, 0], dtype=np.float32) * 0.4
        ).astype(np.uint8)

        # 画编号标签
        for p in all_patches:
            if p["verdict"] == "PASS":
                px1, py1, px2, py2 = p["bbox"]
                pcx, pcy = (px1 + px2) // 2, (py1 + py2) // 2
                label = f"#{p['patch_id']}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)
                cv2.rectangle(preview, (pcx - tw // 2 - 3, pcy - th - 3),
                              (pcx + tw // 2 + 3, pcy + 3), (255, 255, 255), -1)
                cv2.putText(preview, label, (pcx - tw // 2, pcy),
                            font, 0.5, (0, 128, 0), 1)

        preview_path = os.path.join(LOG_DIR, f"{scene_id}_round{round_num}_preview.png")
        cv2.imwrite(preview_path, preview)

        log.log_step("round_summary",
                     f"Round {round_num}: {accepted_count} PASS, {rejected_count} FAIL, "
                     f"累计 {total_pct:.1f}%", round_mask_path)

        log.end_round()

        # 如果所有 4 个 patch 都被拒绝，可能已经没有更多地面了
        if accepted_count == 0:
            print(f"  ⚠️  本轮全部 FAIL，结束迭代")
            break

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

    # 最终预览
    final_preview = img.copy()
    final_preview[ground_mask > 128] = (
        final_preview[ground_mask > 128].astype(np.float32) * 0.6 +
        np.array([0, 200, 0], dtype=np.float32) * 0.4
    ).astype(np.uint8)
    final_preview_path = os.path.join(LOG_DIR, f"{scene_id}_final_preview.png")
    cv2.imwrite(final_preview_path, final_preview)

    # 汇总通过/拒绝的 patch
    passed_patches = [p for p in all_patches if p["verdict"] == "PASS"]
    failed_patches = [p for p in all_patches if p["verdict"] == "FAIL"]
    print(f"  📋 Patch 汇总: {len(passed_patches)} PASS, {len(failed_patches)} FAIL")
    for p in passed_patches:
        print(f"    ✅ {p['patch_id']} (R{p['round']}): {p['area_pct']:.1f}%")
    for p in failed_patches:
        print(f"    ❌ {p['patch_id']} (R{p['round']}): {p.get('reason', '?')[:50]}")

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
    parser = argparse.ArgumentParser(description="LAST SIGNAL - 迭代式地面 Mask 生成器 v2")
    parser.add_argument("--scene", choices=["apartment", "alley"],
                        help="只处理指定场景")
    parser.add_argument("--max-rounds", type=int, default=3,
                        help="最大迭代轮次 (默认 3)")
    parser.add_argument("--no-push", action="store_true",
                        help="不自动 git push")
    args = parser.parse_args()

    print("=" * 60)
    print("🌍 LAST SIGNAL - 迭代式地面 Mask 生成器 v2")
    print("   策略: 4 小 patch/轮 × N 轮，逐块审查")
    print("=" * 60)

    # ── 加载模型 ──
    print("\n🔧 加载模型...")
    sam = MobileSAM()

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
            subprocess.run(["git", "commit", "-m",
                           f"mask: regenerate {scene_id} walkable (iterative v2, per-patch review)"],
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
