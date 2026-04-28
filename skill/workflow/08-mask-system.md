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

---

## 方式一：标准 Mask 生成 (gen_masks.py)

一次性生成所有物体、walkable、water mask。适合已知 bbox 的场景。

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

```bash
python3 scripts/gen_masks.py                    # 完整流程
python3 scripts/gen_masks.py --scene apartment   # 单场景
python3 scripts/gen_masks.py --skip-omni-detect  # 跳过识别
python3 scripts/gen_masks.py --skip-verify       # 跳过验证
```

---

## 方式二：迭代式地面检测 (gen_ground_mask.py)

**适用于 walkable mask 的精确生成。** 每轮 4 个小 patch，逐块审查，通过才叠层。

### 核心思路

每轮只生成 4 个很小的 patch（≤50px），SAM 分割后逐块提交给 Omni 审查。
只有 PASS 的 patch 才叠层到最终 mask，FAIL 的直接丢弃。
下一轮补充 4 个新 patch，2-3 轮完成。

### 流程

```
Round 1:
  ├─ Omni 识别 4 个小 patch (≤50px)
  ├─ SAM 对每个 patch 生成 mask
  ├─ 逐块叠层 + 编号标注:
  │    Patch #p1 → 创建带编号预览 → Omni 审查 → PASS/FAIL
  │    Patch #p2 → 创建带编号预览 → Omni 审查 → PASS/FAIL
  │    Patch #p3 → 创建带编号预览 → Omni 审查 → PASS/FAIL
  │    Patch #p4 → 创建带编号预览 → Omni 审查 → PASS/FAIL
  ├─ PASS 的叠层到 ground_mask，FAIL 的丢弃
  └─ 形态学清理

Round 2 (补充 4 个新 patch):
  └─ 同上，识别未覆盖区域的新 patch

Round 3 (可选):
  └─ 同上

后处理:
  ├─ 减去物体 mask
  ├─ 最终形态学清理
  └─ 输出 walkable_mask
```

### 运行

```bash
python3 scripts/gen_ground_mask.py                    # 两个场景，3 轮
python3 scripts/gen_ground_mask.py --scene apartment   # 单场景
python3 scripts/gen_ground_mask.py --max-rounds 2      # 2 轮
python3 scripts/gen_ground_mask.py --no-push           # 不 git push
```

### 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_PATCH_SIZE` | 50px | 每个 patch 最大尺寸 |
| 每轮 patch 数 | 4 | Omni 每轮识别的 patch 数量 |
| `--max-rounds` | 3 | 最大迭代轮次 |

### 产物

| 文件 | 说明 |
|------|------|
| `ground_detection_logs/{scene}_r{N}_{pid}_mask.png` | 单个 patch 的 SAM mask |
| `ground_detection_logs/{scene}_r{N}_{pid}_review.png` | 带编号的叠层审查图 |
| `ground_detection_logs/{scene}_round{N}_ground.png` | 第 N 轮累计 ground mask |
| `ground_detection_logs/{scene}_round{N}_preview.png` | 带编号的叠层预览 |
| `ground_detection_logs/{scene}_final_preview.png` | 最终结果叠层 |
| `ground_detection_report.pdf` | 全过程 PDF 报告 |

---

## 场景定义

场景配置在两个地方：
- `scripts/gen_masks.py` SCENES — 标准 mask 流程
- `scripts/gen_ground_mask.py` TARGET_SCENES — 迭代地面检测

新增场景时两边都要更新。

---

**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
