# Mask 交互系统

**统一 mask 管线**：MobileSAM (ONNX) 精确分割 + Omni 视觉模型引导 + 叠层验证。

## 技术栈

| 组件 | 用途 |
|------|------|
| MobileSAM (ONNX) | 精确分割 (encoder 27MB + decoder 16MB) |
| mimo-omni | 物体识别 + mask 验证 |

## Mask 类型

| 类型 | 文件名 | 用途 |
|------|--------|------|
| 组合 mask | `{scene}_mask.png` | 所有可交互区域并集 |
| 物体 mask | `{scene}_{obj}_mask.png` | 单个物体精确 mask |
| 可行走 mask | `{scene}_walkable_mask.png` | 角色可行走区域 |
| 水面 mask | `{scene}_water_mask.png` | 水面区域（反射+涟漪） |

白色 (>128) = 有效区域，黑色 = 背景。

## 生成流程

```
bg_{scene}.png
       │
       ▼
Step 1: Omni 物体识别 → bbox
       │
       ▼
Step 2: MobileSAM 精确分割 → binary mask
       │
       ▼
Step 3: 叠层验证 → PASS/FAIL
       │
       ▼
输出: assets/masks/{scene}_{obj}_mask.png
```

## 运行

```bash
python3 gen_masks.py                    # 完整流程
python3 gen_masks.py --scene apartment   # 单场景
python3 gen_masks.py --skip-omni-detect  # 跳过识别
python3 gen_masks.py --skip-verify       # 跳过验证
```

---
**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
