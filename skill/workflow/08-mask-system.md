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

## Walkable Mask 要求

Walkable mask 必须满足两个硬性条件：

### 1. 连通性

Walkable 区域必须是**单一连通域**。不允许出现孤岛或断裂：
- 用 `cv2.connectedComponents` 检查
- 如果存在多个连通域，只保留最大的那个
- 小面积孤岛（<5% 总面积）直接丢弃

### 2. 精确覆盖路面

Walkable mask **只能覆盖实际可行走的地面**，不能覆盖：
- 墙壁、天花板、家具
- 障碍物（桌子、机器、箱子等）
- 装饰物（霓虹灯牌、管道等）

### 3. Omni 叠层验证（必须）

生成后**必须**用 omni 模型验证：将 walkable mask 半透明叠加到场景图上，让 omni 检查：

```bash
# 生成叠层验证图
python3 -c "
from PIL import Image
scene = Image.open('assets/bg_apartment.webp').resize((960,640))
mask = Image.open('assets/masks/apartment_walkable_mask.webp').convert('RGBA')
overlay = Image.new('RGBA', (960,640))
overlay.paste(scene, (0,0))
green = Image.new('RGBA', (960,640), (0,255,0,80))
overlay = Image.composite(green, overlay, mask.convert('L'))
overlay.save('/tmp/verify_walkable.png')
"

# 用 omni 校验
bash mimo_api.sh image /tmp/verify_walkable.png   "绿色半透明区域是角色可行走区域。检查：1. 绿色是否只覆盖地面/路面？2. 有没有覆盖墙壁、家具、障碍物？3. 区域是否连通（没有孤岛）？如有问题请指出具体位置。"
```

**只有 omni 确认 PASS 才能提交。** FAIL 则调整 bbox 重新生成。

## 运行

```bash
python3 scripts/gen_masks.py                    # 完整流程
python3 scripts/gen_masks.py --scene apartment   # 单场景
python3 scripts/gen_masks.py --skip-omni-detect  # 跳过识别
python3 scripts/gen_masks.py --skip-verify       # 跳过验证
```

---
**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
