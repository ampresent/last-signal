# 街道场景 Mask 视觉审计报告

> 分支: `fix/street-mask-visual-audit`
> 日期: 2026-04-26

## 审计方法

对 street 场景的 7 个 mask 逐像素分析，对比 hotspot 位置、walkable 覆盖率、角色可达性、连通性。

---

## 🔴 P0 — 阻塞性 Bug

### 1. Walkable mask 断裂为 6 个不连通区域，spawn 只能到达 8%

**数据**:
- Spawn: (461, 410) — walkable ✅
- Spawn 连通区域: **49,156px (8.0%)**
- 总 walkable: 134,041px (21.8%)
- **6 个不连通区域**:
  - Spawn 组件: 49,156px — 中部偏右
  - 组件 2: 13,984px — 左上角 (0,175)-(86,369)
  - 组件 3: 41,404px — 右下角 (548,489)-(959,639)
  - 组件 4: 29,232px — 左下角 (83,494)-(350,639)
  - 组件 5: 169px — 底部碎片
  - 组件 6: 96px — 底部碎片

**根因**: walkable mask 由 SAM 生成，SAM 将街道分割为多个不连通的区域（人行道、车道、建筑间缝隙），没有做连通性后处理。

### 2. y=440-480 完全无 walkable 像素

**数据**:
- y=440: 8px walkable
- y=450-480: **0px walkable**
- y=480: 恢复到 20,769px

**影响**: spawn 在 y=410，下方 30px 处完全断裂。玩家无法从 spawn 走到街道下半部分（酒吧入口下方区域、垃圾桶、小巷入口）。

### 3. 3/4 个 hotspot 不在 walkable 区域内

| Hotspot | 中心坐标 | walkable? | 在 spawn 组件内？ |
|---------|----------|-----------|-------------------|
| bar_entrance | (250,375) | ❌ val=0 | ❌ |
| road_right | (750,350) | ❌ val=0 | ❌ |
| alley_entrance | (125,550) | ✅ val=255 | ❌ (组件 4) |
| dumpster | (500,450) | ❌ val=0 | ❌ |

**只有 alley_entrance 在 walkable 内，但在另一个不连通组件中。**

玩家从 spawn 出发无法到达任何 hotspot。

### 4. Spawn 组件与水区域不重叠

- water mask 覆盖 y=500-639
- spawn 组件在 y=440 处断裂
- water_overlap 在 y=480-559 达到 98.3%，但这些像素不在 spawn 组件中
- 玩家无法走到水坑区域

---

## 🟡 P1 — 视觉质量问题

### 5. Object mask 过大，大量像素在 hotspot 外

| Mask | 图像覆盖 | hotspot 内 | hotspot 外 |
|------|----------|------------|------------|
| bar_entrance | 18.7% | 77.4% | 29.5% |
| road_right | 31.0% | 97.0% | 38.9% |
| alley_entrance | 6.1% | 54.1% | **78.4%** |
| dumpster | 7.0% | 67.2% | **84.3%** |

- **alley_entrance**: 78.4% 在 hotspot 外 — mask 覆盖了左侧建筑墙壁
- **dumpster**: 84.3% 在 hotspot 外 — mask 覆盖了大片地面而非垃圾桶
- **road_right**: 31% 图像覆盖 — 覆盖了整个右侧区域而非仅仅是路

### 6. Combined mask 包含左侧 edge transition

- combined mask 有 3.1% 的 extra 像素在 x=0-51 区域
- 这是左侧 edge transition（to_alley, zone=left, size=50）
- 逻辑正确，但与 alley_entrance mask 重叠

---

## 🟢 P2 — 建议

### 7. Walkable 与水区域高度重叠

- y=480-559: walkable 中 98.3% 同时在 water mask 中
- y=560-639: 100% 重叠
- 这是预期行为（街道积水区域可行走），但需要确认游戏逻辑是否正确处理

---

## 修复建议

| # | 问题 | 严重度 | 修复方案 |
|---|------|--------|----------|
| 1 | Walkable 6 个不连通区域 | 🔴 P0 | 重做 walkable mask（矩形方案 + 障碍物减除）|
| 2 | y=440-480 断裂 | 🔴 P0 | 同上 |
| 3 | 3/4 hotspot 不可达 | 🔴 P0 | 同上 |
| 4 | Spawn 与水区域断开 | 🔴 P0 | 同上 |
| 5 | Object mask 过大 | 🟡 P1 | 缩小 bbox |
