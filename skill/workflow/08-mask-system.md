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

**适用于 walkable mask 的精确生成。** 通过多轮 Omni + SAM 迭代，逐步识别地面区域。

### 核心思路

传统方式用一个大 bbox 做 SAM 分割，容易把墙壁、家具也包含进去。
迭代方式让 Omni 先识别多个**小的**地面 patch（80x80px），SAM 对每个小 patch 精确分割，
然后 Omni 审查叠层结果，决定是否需要补充或修正。

### 流程

```
bg_{scene}.png
       │
       ▼
Round 1:
  ├─ Omni 识别 8-15 个小地面 patch (≤80px each)
  ├─ SAM 对每个 patch 生成 mask
  ├─ 叠层到 cumulative mask (OR 操作)
  ├─ 形态学清理 (CLOSE + OPEN)
  └─ Omni 审查: PASS / FAIL + MISSING/OVERCOVER 建议
       │
       ▼
Round 2 (如果 Round 1 FAIL):
  ├─ Omni 参考已有 mask，识别遗漏区域
  ├─ SAM 分割新 patch
  ├─ 叠层到 cumulative mask
  ├─ 移除 OVERCOVER 区域
  └─ Omni 审查
       │
       ▼
Round 3 (如果 Round 2 FAIL):
  └─ 同上，最多 3 轮
       │
       ▼
后处理:
  ├─ 减去物体 mask (terminal, window, door...)
  ├─ 最终形态学清理
  └─ 输出: assets/masks/{scene}_walkable_mask.png
```

### 运行

```bash
# 两个场景都跑（默认 3 轮）
python3 scripts/gen_ground_mask.py

# 单场景
python3 scripts/gen_ground_mask.py --scene apartment
python3 scripts/gen_ground_mask.py --scene alley

# 指定轮次
python3 scripts/gen_ground_mask.py --max-rounds 2

# 不自动 git push
python3 scripts/gen_ground_mask.py --no-push
```

### 关键参数调优

**Patch 大小**：默认 80x80px。太大会包含非地面区域（墙壁、家具），太小则需要更多 patch 才能覆盖。
在 `omni_identify_ground_patches()` 的 prompt 中调整 `MAX_PATCH_SIZE`。

**Patch 数量**：默认 8-15 个/轮。数量多 → 覆盖更全面，但 API 调用时间更长。
在 prompt 中调整 `返回 N-M 个`。

**空间分布**：prompt 中强调"分散在整个地面区域，不要只集中在某一处"，
避免 Omni 只识别最近/最明显的区域。

### 产物

| 文件 | 说明 |
|------|------|
| `ground_detection_logs/{scene}_log_*.json` | 完整过程日志（每轮 bbox、mask 面积、审查结果） |
| `ground_detection_logs/{scene}_r{N}_patch{M}_mask.png` | 单个 patch 的 SAM mask |
| `ground_detection_logs/{scene}_round{N}_ground.png` | 第 N 轮累计 ground mask |
| `ground_detection_logs/{scene}_round{N}_preview.png` | 第 N 轮绿色叠层预览 |
| `ground_detection_logs/{scene}_round{N}_review.png` | Omni 审查用图 |
| `ground_detection_logs/{scene}_final_preview.png` | 最终结果叠层 |
| `ground_detection_report.pdf` | 全过程 PDF 报告（英文） |

### Omni 审查机制

Omni 审查时看到的是：原图 + 绿色半透明叠层（已识别地面）。

审查输出格式：
- `PASS` — 覆盖准确，无需更多轮次
- `FAIL` — 需要改进
- `MISSING [x1,y1,x2,y2] <描述>` — 遗漏区域（下一轮补充）
- `OVERCOVER [x1,y1,x2,y2] <描述>` — 误覆盖区域（立即从 mask 中移除）

### 已知限制

1. **Omni 倾向于识别底部区域**（近景地面），对远处/高处地面识别较弱
2. **API 超时**：mimo_api.sh 默认 timeout=300s，大图可能需要更长时间
3. **空结果重试**：Omni 偶尔返回空结果，脚本内置了重试逻辑
4. **覆盖率**：典型场景 10-20% 覆盖率（游戏 walkable 区域通常只占场景的一部分）

---

## 场景定义

场景配置在两个地方：
- `scripts/gen_masks.py` SCENES — 标准 mask 流程
- `scripts/gen_ground_mask.py` TARGET_SCENES — 迭代地面检测

新增场景时两边都要更新。

---

**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
