# 公寓场景 Mask 视觉审计报告

> 分支: `fix/apartment-mask-visual-audit`
> 日期: 2026-04-26

## 审计方法

对 apartment 场景的 5 个 mask 逐像素分析，对比 hotspot 位置、walkable 覆盖率、角色可达性。

---

## 🔴 P0 — 阻塞性 Bug

### 1. Walkable mask 覆盖率仅 14%，玩家无法到达窗户和门

**数据**:
- `apartment_walkable_mask.webp` 覆盖率: **14.0%** (86,086 / 614,400 px)
- Walkable 区域质心: (589, 320)，集中在画面中右侧
- 四象限覆盖: Q1=2.6%, Q2=31.8%, Q3=7.4%, Q4=14.3%

**Hotspot 可达性**:

| Hotspot | 中心坐标 | 可达？ | Hotspot 内 walkable 占比 |
|---------|----------|--------|--------------------------|
| terminal | (475, 350) | ✅ | 40.0% |
| window | (150, 525) | ❌ | 0.0% |
| door | (825, 425) | ❌ | 6.6% |

**角色移动能力** (spawn 499,364):
- 向左 50px: ❌ blocked
- 向右 50px: ✅
- 向下 50px: ✅
- 向左下: ❌ blocked
- y=400 以下只剩 x=500 附近一条极窄通道

**根因**: walkable mask 由 gen_masks.py 的 MobileSAM 生成，SAM 只识别了房间中央的一小块地板区域，没有覆盖整个房间地面。窗边区域（左侧暗色地板）和门区域（右侧）完全被排除。

**对比**: gen_walk_masks.py 的矩形方案覆盖 38.0%（减去 terminal 障碍物后），window 可达 77%，door 可达 20%。

**修复方案**: 
- **方案 A**: 用 gen_walk_masks.py 的矩形 walkable mask 替换 SAM 版本
- **方案 B**: 扩大 gen_masks.py 的 walkable bbox 并重新运行 SAM（需要模型文件）
- **推荐方案 A**：立即可用，且矩形 mask 对公寓这种室内场景更合理

### 2. Walkable mask 与 Combined mask 在底部重叠 80.9%

**数据**:
- y=560-639 区域: walkable 内有 8,913 px，其中 7,213 px (80.9%) 同时在 combined mask 中
- 这意味着底部的 walkable 区域和物体 mask 大面积重叠

**根因**: combined mask 包含了 edge transition（底部 y=589-639 的出口区域），而 walkable mask 没有排除这个区域。

**影响**: 玩家在底部边缘行走时，可能触发物体交互而非场景切换。

### 3. Character 网格中 y=400 以下只有 x=500 一列可走

**数据**:
- y=200-399: x=500-750 区域可走（宽 250px 的走廊）
- y=400-550: 只有 x=500 一列可走（1px 宽的线）
- y=550-600: x=450-500 恢复一小块

**影响**: 角色在 y>400 后无法横向移动，被锁死在一条垂直线上。这在视觉上和交互上都是严重问题。

---

## 🟡 P1 — 视觉质量问题

### 4. Terminal mask 过大，超出物体实际边界

**数据**:
- Terminal mask bbox: (497,360)-(959,636) — 覆盖了画面右下角 42%
- Terminal hotspot: (350,250)-(600,450)
- Mask 在 hotspot 内: 只有 15.0%
- Mask 在 hotspot 外: 93.6%

**影响**: terminal mask 覆盖了大量不属于终端的区域（地板、墙壁），导致：
- debug 模式下这些区域显示为红色叠层
- 如果有基于 mask 的点击检测，会误判

**根因**: SAM 分割时 bbox [500, 380, 900, 627] 太大，包含了终端桌面及其周围区域。

### 5. Window mask 覆盖面积 35%，包含窗户以外区域

**数据**:
- Window mask bbox: (0,136)-(472,636) — 画面左侧 35%
- Window hotspot: (50,450)-(250,600)
- Mask 在 hotspot 内: 100%（全覆盖）
- Mask 在 hotspot 外: 86.0%

**影响**: mask 远大于 hotspot 定义的交互区域。debug 模式下大面积显示为蓝色叠层。

### 6. Door mask 与 hotspot 对齐度较好但偏大

**数据**:
- Door mask bbox: (776,132)-(959,633)
- Door hotspot: (750,300)-(900,550)
- Mask 在 hotspot 内: 71.2%
- Mask 在 hotspot 外: 66.1%

**影响**: 门 mask 从 y=132 开始，覆盖了门框上方的墙壁区域。

---

## 🟢 P2 — 建议优化

### 7. Combined mask 底部 edge transition 区域 (y=589-639) 全覆盖

- 13,583 个 extra 像素全部在 y=589-639
- 这是 `add_edge_transition(combined, "bottom", 50, w, h)` 产生的
- 用于场景切换检测，逻辑正确
- 但与 walkable mask 重叠（见 P0-2）

### 8. 背景图尺寸 940×627 vs mask 尺寸 960×640

- 背景图在加载时被 resize 到 960×640
- 10px 的差异可能导致 mask 与场景有微小偏移
- 实际影响很小（约 1% 的缩放）

---

## 修复优先级

| # | 问题 | 严重度 | 修复难度 |
|---|------|--------|----------|
| 1 | Walkable mask 仅 14%，window/door 不可达 | 🔴 P0 | 中 — 需替换为矩形方案 |
| 2 | Walkable 与 combined 底部重叠 80% | 🔴 P0 | 低 — walkable 排除 edge zone |
| 3 | y=400 以下只有 1px 宽通道 | 🔴 P0 | 同 #1 |
| 4 | Terminal mask 过大 | 🟡 P1 | 中 — 需调整 bbox |
| 5 | Window mask 偏大 | 🟡 P1 | 低 — 缩小 bbox |
| 6 | Door mask 偏大 | 🟡 P1 | 低 — 缩小 bbox |
