#!/usr/bin/env python3
"""
LAST SIGNAL — Water Mask 生成器（纯几何）
根据 VFX SCENE_CONFIG 中的 puddleReflection.y 参数，
从该 Y 坐标到画面底部生成白色 water mask。

用法:
    python3 gen_water_masks.py              # 生成所有有 puddleReflection 的场景
    python3 gen_water_masks.py --scene street  # 单个场景
"""
import cv2
import numpy as np
import os
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASK_DIR = os.path.join(BASE_DIR, "assets", "masks")
os.makedirs(MASK_DIR, exist_ok=True)

W, H = 960, 640

# 从 VFX SCENE_CONFIG 中提取的 puddleReflection 配置
WATER_SCENES = {
    "street": {"y": 500},
    "alley": {"y": 520},
    "tower": {"y": 530},
    "rooftop": {"y": 510},
}


def gen_water_mask(scene_id, cfg):
    """生成 water mask: 从 puddleReflection.y 到画面底部"""
    mask = np.zeros((H, W), dtype=np.uint8)
    water_y = cfg["y"]
    mask[water_y:H, :] = 255
    return mask


def main():
    parser = argparse.ArgumentParser(description="Water Mask 生成器")
    parser.add_argument("--scene", type=str, help="生成单个场景")
    parser.add_argument("--force", action="store_true", help="覆盖已有文件")
    args = parser.parse_args()

    print("=" * 50)
    print("💧 LAST SIGNAL — Water Mask 生成器")
    print("=" * 50)

    scenes = {args.scene: WATER_SCENES[args.scene]} if args.scene else WATER_SCENES
    ok, skip = 0, 0

    for scene_id, cfg in scenes.items():
        out_path = os.path.join(MASK_DIR, f"{scene_id}_water_mask.webp")

        if os.path.exists(out_path) and not args.force:
            print(f"⏭️  {scene_id}: 已有 {out_path}")
            skip += 1
            continue

        mask = gen_water_mask(scene_id, cfg)
        cv2.imwrite(out_path, mask)

        pct = np.count_nonzero(mask) / (W * H) * 100
        print(f"✅ {scene_id}: {out_path} (水面 {pct:.0f}%, y={cfg['y']})")
        ok += 1

    print(f"\n{'='*50}")
    print(f"✅ 生成: {ok}  ⏭️  跳过: {skip}")


if __name__ == "__main__":
    main()
