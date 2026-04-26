# 角色出生点系统

每个场景中角色的初始化位置**从 walkable mask 中随机选取**，每次进入场景都会重新随机。

## 工作原理

1. 进入场景时，调用 `Game.getRandomSpawn(sceneId)`
2. 扫描 `walkable_mask` 中所有白色像素（可行走区域）
3. 随机选取一个像素，归一化为 [0, 1] 坐标
4. 设置为角色当前位置（留 2% 边距避免贴边）

## 代码

```javascript
getRandomSpawn(sceneId) {
  const maskObj = this.masks[`${sceneId}_walkable`];
  if (!maskObj || !maskObj.data) return [0.5, 0.75];
  const data = maskObj.data.data;
  const w = maskObj.data.width;
  const h = maskObj.data.height;
  const walkable = [];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (data[(y * w + x) * 4] > 128) walkable.push([x, y]);
    }
  }
  if (walkable.length === 0) return [0.5, 0.75];
  const [px, py] = walkable[Math.floor(Math.random() * walkable.length)];
  return [px / w, py / h];
}
```

## 构建时采样（gen_masks.py）

`gen_masks.py` 在生成 walkable mask 后也会随机采样一个 spawn 位置写入 `mask_metadata.json`，
用于文档参考。但游戏运行时使用实时随机选取。

```python
def _random_walkable_spawn(mask_path):
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    ys, xs = np.where(mask > 128)
    idx = np.random.randint(len(xs))
    return [xs[idx] / mask.shape[1], ys[idx] / mask.shape[0]]
```

## 场景连接图

```
apartment ←→ street ←→ bar
                ↕
             alley

              tower ←→ server ←→ rooftop
                ↕
             underground → core
```

每个场景的出生点都是随机的，不区分来源场景。

---
**Related reference:** [gameplay](../reference/gameplay.md)
