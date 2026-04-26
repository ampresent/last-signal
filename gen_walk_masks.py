"""
LAST SIGNAL - 行走区域 Mask 生成器
从场景交互 mask 合成角色行走区域 mask

用法:
    python3 gen_walk_masks.py              # 生成所有场景
    python3 gen_walk_masks.py --scene apartment  # 单个场景

输出: assets/masks/{scene}_walkable_mask.png
白色(255) = 可行走, 黑色(0) = 不可行走
"""
import cv2
import numpy as np
import os
import sys
import argparse

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASK_DIR = os.path.join(_BASE_DIR, "assets", "masks")
ASSET_DIR = os.path.join(_BASE_DIR, "assets")

# ── 场景行走区域定义 ──
# 每个场景定义:
#   walkable_rects: 可行走的矩形区域 (x1, y1, x2, y2) 归一化坐标
#   obstacle_masks: 障碍物 mask (不可行走的物体)
#   edge_zones: 边缘过渡区域 (连接其他场景)

SCENE_WALK = {
    "apartment": {
        # 公寓: 房间内部区域
        "walkable_rects": [
            (0.1, 0.3, 0.9, 0.95),   # 主房间
        ],
        "obstacle_masks": [
            "apartment_terminal_mask.png",  # 终端机
        ],
        # 门的位置 (可触发场景切换)
        "edge_zones": [
            {"rect": (0.4, 0.85, 0.6, 0.95), "target": "street"},
        ],
    },
    "street": {
        # 街道: 宽敞的街道区域
        "walkable_rects": [
            (0.05, 0.25, 0.95, 0.95),   # 街道主体
        ],
        "obstacle_masks": [
            "street_dumpster_mask.png",   # 垃圾桶
        ],
        "edge_zones": [
            {"rect": (0.0, 0.3, 0.08, 0.7), "target": "alley"},
            {"rect": (0.05, 0.15, 0.35, 0.45), "target": "bar"},
        ],
    },
    "bar": {
        "walkable_rects": [
            (0.1, 0.3, 0.9, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [
            {"rect": (0.85, 0.3, 1.0, 0.7), "target": "street"},
        ],
    },
    "alley": {
        "walkable_rects": [
            (0.1, 0.2, 0.9, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [
            {"rect": (0.9, 0.3, 1.0, 0.7), "target": "street"},
        ],
    },
    "tower": {
        # 塔楼广场
        "walkable_rects": [
            (0.15, 0.3, 0.85, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [],
    },
    "server": {
        # 服务器机房
        "walkable_rects": [
            (0.1, 0.2, 0.9, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [],
    },
    "rooftop": {
        "walkable_rects": [
            (0.1, 0.2, 0.9, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [],
    },
    "office": {
        "walkable_rects": [
            (0.1, 0.25, 0.9, 0.9),
        ],
        "obstacle_masks": [],
        "edge_zones": [],
    },
}


def gen_walk_mask(scene_id, cfg):
    """生成一个场景的行走 mask"""
    W, H = 960, 640
    mask = np.zeros((H, W), dtype=np.uint8)

    # 1. 绘制可行走矩形区域
    for (x1n, y1n, x2n, y2n) in cfg["walkable_rects"]:
        x1, y1 = int(x1n * W), int(y1n * H)
        x2, y2 = int(x2n * W), int(y2n * H)
        mask[y1:y2, x1:x2] = 255

    # 2. 减去障碍物 mask
    for obs_file in cfg.get("obstacle_masks", []):
        obs_path = os.path.join(MASK_DIR, obs_file)
        if os.path.exists(obs_path):
            obs = cv2.imread(obs_path, cv2.IMREAD_GRAYSCALE)
            if obs is not None:
                obs = cv2.resize(obs, (W, H))
                mask[obs > 128] = 0

    # 3. 保留边缘过渡区 (不减去)
    for ez in cfg.get("edge_zones", []):
        (x1n, y1n, x2n, y2n) = ez["rect"]
        x1, y1 = int(x1n * W), int(y1n * H)
        x2, y2 = int(x2n * W), int(y2n * H)
        mask[y1:y2, x1:x2] = 255

    # 4. 形态学处理: 平滑边缘
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # 5. 高斯模糊边缘 (软边界)
    mask = cv2.GaussianBlur(mask, (3, 3), 0)

    return mask


def main():
    parser = argparse.ArgumentParser(description="行走区域 Mask 生成器")
    parser.add_argument("--scene", type=str, help="生成单个场景")
    args = parser.parse_args()

    print("=" * 50)
    print("🚶 LAST SIGNAL - 行走区域 Mask 生成器")
    print("=" * 50)

    scenes = {args.scene: SCENE_WALK[args.scene]} if args.scene else SCENE_WALK
    ok, fail = 0, 0

    for scene_id, cfg in scenes.items():
        out_path = os.path.join(MASK_DIR, f"{scene_id}_walkable_mask.png")

        # 跳过已存在
        if os.path.exists(out_path) and "--force" not in sys.argv:
            print(f"⏭️  {scene_id}: 已有 {out_path}")
            ok += 1
            continue

        try:
            mask = gen_walk_mask(scene_id, cfg)
            cv2.imwrite(out_path, mask)

            # 统计
            walkable_pct = np.sum(mask > 128) / (960 * 640) * 100
            print(f"✅ {scene_id}: {out_path} (可行走 {walkable_pct:.0f}%)")
            ok += 1
        except Exception as e:
            print(f"❌ {scene_id}: {e}")
            fail += 1

    print(f"\n{'='*50}")
    print(f"✅ 成功: {ok}  ❌ 失败: {fail}")

    # 显示如何在 index.html 中配置
    if not args.scene:
        print(f"\n💡 提示: 在 SCENES 的场景中添加 characters 配置:")
        print("""
    characters: [{
      id: 'kai',
      x: 0.5, y: 0.7,
      dir: 'down',
      speed: 0.12,
      scale: 0.22,
    }],
        """)


if __name__ == "__main__":
    main()
