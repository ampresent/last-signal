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

## Walkable Mask 生成策略

### 推荐流程（经过验证）

```
Step 1: MobileSAM 在 walkable bbox 内分割 → 初始 mask
Step 2: 空间裁剪 — 裁掉顶部墙壁/天花板区域 (crop_top_pct)
Step 3: 减去障碍物 object masks（已有的物体 mask）
Step 4: 形态学清理 (MORPH_CLOSE 11×11 + MORPH_OPEN 5×5)
Step 5: 连通性强制 — 只保留最大连通域
Step 6: 缩放到游戏尺寸 (960×640) 并保存
Step 7: 生成半透明叠层验证图 (绿色 overlay)
Step 8: Omni 视觉模型验证 — PASS/FAIL
```

### 关键参数（经校准）

| 场景 | walkable_bbox | crop_top_pct | 覆盖率 |
|------|---------------|--------------|--------|
| apartment | [120, 480, 850, 627] | 0.55 | 5.5% |
| street | [30, 200, 930, 627] | 0.35 | 27.9% |
| bar | 需手动处理 | — | ~15% |
| alley | [300, 300, 750, 627] | 0.35 | 20.7% |
| tower | [100, 250, 900, 627] | 0.40 | 43.4% |
| server | [240, 157, 900, 627] | 0.25 | 31.3% |
| rooftop | [100, 450, 880, 627] | 0.60 | 13.5% |

### ⚠️ 已知陷阱

#### 1. 深度图不能用于区分 walkable/non-walkable

深度图测量的是**距相机距离**，不是地面高度。Walkable 区域的深度范围极宽（p5-p95: 0.32–0.86），无法用阈值分割。

**错误做法**: `depth_mask = (depth >= 0.3) & (depth <= 0.85)` — 会把墙壁也包含进来。

**正确做法**: 用 MobileSAM bbox + 空间裁剪 (crop_top_pct) 作为主要约束。

#### 2. 障碍物"坐在"walkable 区域上

当障碍物（如凳子、桌子）直接放在地面上时，MobileSAM 无法区分"障碍物底部"和"地面"——它们在像素级别融合。

**受影响场景**: bar（吧台凳）

**解决方案**:
- 方案A: 用 MobileSAM 对每个障碍物单独用小 bbox 分割，生成障碍物 mask，再从 walkable 减除
- 方案B: 手动标注障碍物像素位置
- 方案C: 在游戏引擎碰撞体层面处理

#### 3. bbox 太大会覆盖墙壁

MobileSAM 把 bbox 内的整个区域视为一个连通表面。如果 bbox 包含墙壁区域，墙壁也会被标记为 walkable。

**解决**: bbox 应该只包含地面区域，用 crop_top_pct 裁掉顶部。

#### 4. Omni 验证非常严格

即使只有少量像素与障碍物重叠，Omni 也会判定 FAIL。需要精确的物体 mask 减除。

## 运行

```bash
python3 scripts/gen_masks.py                    # 完整流程
python3 scripts/gen_masks.py --scene apartment   # 单场景
python3 scripts/gen_masks.py --skip-omni-detect  # 跳过识别
python3 scripts/gen_masks.py --skip-verify       # 跳过验证
```

---
**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
