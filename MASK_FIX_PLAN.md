# Mask 体系修复计划

> 分支: `fix/mask-system-audit`
> 审计日期: 2026-04-26

## 问题清单

### 🔴 P0 — 阻塞性 Bug

#### Fix 1: `waterMasks` 从未加载 — 水面效果完全失效
- **文件**: `index.html`
- **问题**: `Game.waterMasks` 在 L2417 声明为 `{}`，但 `loadAssets()` 中没有任何代码加载 water mask
- **影响**: street/alley/tower/rooftop 的积水反射效果靠硬编码 fallback，雨滴 splash 不触发
- **修复**: 在 `loadAssets()` 的场景加载流程中，添加 water mask 加载（类似 walkable mask）

#### Fix 2: Debug 模式硬编码为 `true`
- **文件**: `index.html` L2299
- **问题**: `DebugLogger.enabled: true` 硬编码，注释写的是 "?debug 参数启用"
- **影响**: 所有玩家看到 debug overlay（绿色 walkable 叠层、黄色 object 边缘、标签文字）
- **修复**: 改为 `enabled: new URLSearchParams(location.search).has('debug')`

#### Fix 3: 缺失的 water mask 文件
- **文件**: `gen_masks.py`, `assets/masks/`
- **问题**: metadata 引用了 5 个 water mask 但磁盘上不存在
  - `street_water_mask.webp`
  - `alley_water_mask.webp`
  - `tower_water_mask.webp`
  - `rooftop_water_mask.webp`
  - `maintenance_water_mask.webp`
- **修复**: 确认 gen_masks.py 能生成这些文件（water 配置已存在，需要实际运行生成）

### 🟡 P1 — 逻辑偏差

#### Fix 4: gen_walk_masks.py 场景命名与游戏引擎不一致
- **文件**: `gen_walk_masks.py`
- **问题**: `tower_exterior` → 应为 `tower`，`server_room` → 应为 `server`
- **影响**: tower 场景的 walkable mask 文件名为 `tower_exterior_walkable_mask.webp`，游戏引擎找不到
- **修复**: 重命名 SCENE_WALK 中的 key，同步重命名磁盘上的文件

#### Fix 5: mask_metadata.json 引用 `.png` 但实际文件是 `.webp`
- **文件**: `gen_masks.py` 的 `save_metadata()` 函数
- **问题**: metadata 写 `masks/xxx_mask.png`，实际文件是 `.webp`
- **修复**: 修改 `save_metadata()` 输出 `.webp` 扩展名

#### Fix 6: gen_walk_masks.py 硬编码绝对路径
- **文件**: `gen_walk_masks.py` L16-17
- **问题**: `MASK_DIR = "/root/.openclaw/workspace/last-signal/assets/masks"`
- **修复**: 改为基于 `__file__` 的相对路径

### 🟢 P2 — 清理

#### Fix 7: 清理孤儿 mask 文件
- **文件**: `assets/masks/`
- **问题**: 约 26 个 mask 文件不被游戏引擎使用（echo_lobby, maintenance, data_haven, flashback, hospital, office, core 等）
- **修复**: 删除孤儿文件，保留游戏引擎实际引用的 mask

#### Fix 8: core 场景 mask — 无需修复
- **结论**: core 场景 hotspots 为空数组，纯对话场景
- 全白 walkable（全区可走）+ 全黑 scene mask（无物体障碍）合理
- 不需要生成 object mask
- **文件**: `assets/masks/core_mask.webp`, `core_walkable_mask.webp`
- **问题**: core_mask 全黑（0% 覆盖），core_walkable 全白（100% 覆盖）
- **修复**: 需要为 core 场景生成有意义的 mask，或标记为 TODO

---

## 执行顺序

1. Fix 2 — Debug 硬编码（一行改动，低风险）
2. Fix 5 — metadata 扩展名（.png → .webp）
3. Fix 6 — 硬编码绝对路径
4. Fix 4 — 场景命名统一（tower_exterior → tower）
5. Fix 1 — waterMasks 加载逻辑
6. Fix 3 — 生成缺失的 water mask 文件
7. Fix 7 — 清理孤儿文件
8. Fix 8 — core 场景 mask
