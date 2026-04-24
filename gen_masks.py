#!/usr/bin/env python3
"""
LAST SIGNAL - 基于 GrabCut 的精细 Mask 生成器
使用 OpenCV GrabCut 基于图像内容进行精细分割，以视觉模型识别的区域为引导。
每个场景生成：
  - 组合 mask (sceneId_mask.png): 所有可交互区域 + 边缘过渡
  - 单独 mask (sceneId_objId_mask.png): 每个物体的精确 mask
输出精确的非矩形 mask。

依赖: pip install opencv-python-headless numpy pillow
"""

import cv2
import numpy as np
import json
import os

IMG_W, IMG_H = 940, 627       # AI 生成图片原始尺寸
GAME_W, GAME_H = 960, 640     # 游戏画布尺寸
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MASK_DIR = os.path.join(ASSETS_DIR, "masks")
os.makedirs(MASK_DIR, exist_ok=True)

# ============================================================
# 场景交互区域定义
#
# 坐标基于 AI 生成图片 (940x627)。
# bbox 由视觉模型 (mimo-omni) 识别后人工调整。
#
# objects: 场景中的可交互物体
#   - id:    英文标识，与 index.html 中 hotspot 的 maskId 对应
#   - label: 中文显示名
#   - bbox:  [x1, y1, x2, y2] GrabCut 初始边界框
#
# edge_transitions: 场景边缘过渡区域
#   - zone:  bottom/top/left/right
#   - size:  过渡区域像素宽度
#   - target: 目标场景 ID
# ============================================================

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

    # ── 新增场景 ──

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


def grabcut_segment(img, bbox, iter_count=5):
    """
    使用 GrabCut 对边界框内区域进行精细分割。
    返回二值 mask (0=背景, 255=前景)。
    """
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

    # 形态学清理
    result = cv2.morphologyEx(
        result, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    result = cv2.morphologyEx(
        result, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )

    # 高斯模糊软化边缘
    result = cv2.GaussianBlur(result, (5, 5), 0)
    _, result = cv2.threshold(result, 127, 255, cv2.THRESH_BINARY)
    return result


def add_edge_transition(mask, zone, size, w, h):
    """在 mask 指定边缘添加过渡区域"""
    if zone == "bottom":
        mask[h - size:h, :] = 255
    elif zone == "top":
        mask[0:size, :] = 255
    elif zone == "left":
        mask[:, 0:size] = 255
    elif zone == "right":
        mask[:, w - size:w] = 255


def process_scene(scene_id, data):
    """处理单个场景，生成组合 mask + 每个物体的单独 mask + walkable + water"""
    img_path = os.path.join(ASSETS_DIR, data["image"])
    if not os.path.exists(img_path):
        print(f"  ❌ 图片不存在: {img_path}")
        return

    img = cv2.imread(img_path)
    if img is None:
        print(f"  ❌ 无法读取: {img_path}")
        return

    h, w = img.shape[:2]
    combined = np.zeros((h, w), np.uint8)

    for obj in data["objects"]:
        bbox = obj["bbox"]
        seg = grabcut_segment(img, bbox)
        ratio = np.count_nonzero(seg) / (h * w) * 100

        # 质量检查 + fallback
        if ratio < 0.05:
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = bbox
            seg[y1:y2, x1:x2] = 255
        elif ratio > 35:
            x1, y1, x2, y2 = bbox
            mx, my = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
            s2 = grabcut_segment(img, [x1 + mx, y1 + my, x2 - mx, y2 - my])
            s2_ratio = np.count_nonzero(s2) / (h * w) * 100
            if 0.05 < s2_ratio < 35:
                seg = s2
                ratio = s2_ratio
            else:
                seg = np.zeros((h, w), np.uint8)
                seg[y1:y2, x1:x2] = 255

        # 保存单独 mask（缩放到游戏尺寸）
        obj_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png"), obj_game)

        combined = cv2.bitwise_or(combined, seg)
        print(f"  🎯 {obj['label']} ({obj['id']}): {ratio:.1f}%")

    # ── Walkable 区域 ──
    walkable_cfg = data.get("walkable")
    if walkable_cfg:
        seg = grabcut_segment(img, walkable_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 1.0:
            # GrabCut 失败，fallback 到矩形
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = walkable_cfg["bbox"]
            seg[y1:y2, x1:x2] = 255
        # 减去不可行走的物体 mask（obstacle）
        for obj in data["objects"]:
            obj_mask_path = os.path.join(MASK_DIR, f"{scene_id}_{obj['id']}_mask.png")
            if os.path.exists(obj_mask_path):
                obs = cv2.imread(obj_mask_path, cv2.IMREAD_GRAYSCALE)
                if obs is not None:
                    obs = cv2.resize(obs, (w, h), interpolation=cv2.INTER_NEAREST)
                    seg[obs > 128] = 0
        # 形态学平滑
        seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        seg = cv2.morphologyEx(seg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        walkable_game = cv2.resize(seg, (GAME_W, GAME_H), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.png"), walkable_game)
        walk_pct = np.count_nonzero(walkable_game) / (GAME_W * GAME_H) * 100
        print(f"  🚶 walkable ({walkable_cfg['label']}): {walk_pct:.1f}%")

    # ── Water 水面区域 ──
    water_cfg = data.get("water")
    if water_cfg:
        seg = grabcut_segment(img, water_cfg["bbox"])
        ratio = np.count_nonzero(seg) / (h * w) * 100
        if ratio < 0.3:
            # GrabCut 没能分割出水面，fallback 到矩形
            seg = np.zeros((h, w), np.uint8)
            x1, y1, x2, y2 = water_cfg["bbox"]
            seg[y1:y2, x1:x2] = 255
        # 形态学平滑
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


def main():
    print("=" * 60)
    print("🎭 LAST SIGNAL - GrabCut 精细 Mask 生成器")
    print("=" * 60)

    for scene_id, data in SCENES.items():
        print(f"\n🎬 {scene_id}")
        process_scene(scene_id, data)

    # 保存元数据
    meta = {}
    for sid, sd in SCENES.items():
        objects = [
            {"id": o["id"], "label": o["label"],
             "mask": f"masks/{sid}_{o['id']}_mask.png"}
            for o in sd["objects"]
        ]
        # walkable 和 water 也写入元数据
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

    total_obj = sum(len(s["objects"]) for s in SCENES.values())
    total_edge = sum(len(s.get("edge_transitions", [])) for s in SCENES.values())
    print(f"\n✅ 完成: {total_obj} 个物体 + {total_edge} 个边缘过渡")
    print(f"📁 {MASK_DIR}")


if __name__ == "__main__":
    main()
