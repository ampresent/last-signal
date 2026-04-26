# 角色出生点系统

每个场景中角色的初始化位置根据**上一场景的出口位置**动态决定，而非固定坐标。

## 工作原理

1. `goScene(targetScene, sourceScene)` 接受来源场景参数
2. 查询 `Game.SPAWN_MAP[targetScene][sourceScene]` 获取出生点坐标
3. 如果有配置，覆盖场景默认的 `characters[0].x/y`
4. 如果没有配置（如首次加载），使用场景默认位置

## 场景连接图

```
apartment ←→ street ←→ bar
                ↕
             alley

              tower ←→ server ←→ rooftop
                ↕
             underground → core
```

## 出生点配置 (SPAWN_MAP)

| 目标场景 | 来源场景 | 出生位置 | 说明 |
|---------|---------|---------|------|
| apartment | rooftop | (0.52, 0.57) | 从楼顶回来 → 公寓中央 |
| street | apartment | (0.15, 0.70) | 从公寓出门 → 街道左侧 |
| street | bar | (0.22, 0.65) | 从酒吧出来 → 酒吧门口 |
| street | tower | (0.85, 0.70) | 从塔回来 → 街道右侧 |
| street | alley | (0.10, 0.70) | 从小巷出来 → 小巷入口旁 |
| bar | street | (0.85, 0.75) | 从街道进来 → 酒吧出口附近 |
| alley | street | (0.85, 0.75) | 从街道进来 → 小巷出口附近 |
| tower | street | (0.20, 0.70) | 从街道过来 → 左侧入口 |
| tower | server | (0.50, 0.80) | 从服务器室上来 → 中央 |
| server | tower | (0.20, 0.85) | 从塔楼进来 → 左侧入口 |
| server | rooftop | (0.80, 0.85) | 从楼顶下来 → 右侧通道口 |
| rooftop | server | (0.50, 0.80) | 从服务器室上来 → 中央 |

## 添加新场景时

1. 在 `SPAWN_MAP` 中添加目标场景的出生点配置
2. 配置所有可能来源场景的入口位置
3. 在来源场景的 `goScene` 调用中传入 `'source_scene_id'`

---
**Related reference:** [gameplay](../reference/gameplay.md)
