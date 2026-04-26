# Sprite Sheet 生成工作流（视频→sprite sheet）

将角色行走视频转换为带方向的 sprite sheet。这是角色动画素材的**唯一生成管线**。

## 0. 素材准备：生成方向视频

> ⚠️ 在执行后续步骤之前，需要先在 AI 平台生成各方向的角色行走视频。

**推荐平台：** 豆包（字节跳动）、即梦 APP（字节跳动）

**生成流程：**

1. **生成角色正面图** — 文生图生成角色正面立绘
2. **图生图生成四个方向图** — front / back / left / right
3. **方向图生视频** — 提示词：`生成视频：朝他面向的方向走路，作为标准素材使用，镜头保持角色在正中央，单镜头`

**关键要求：**
- 镜头固定，角色保持在画面正中央
- 单镜头，不要切换
- **必须使用绿幕背景**（纯绿色，RGB ≈ 0,255,0）
- 每个方向单独生成一个视频文件

命名：`{character}_{direction}.mov`（如 `joker_front.mov`）

## 1. 提取帧

```bash
ffmpeg -y -i input.mov -vf "scale=目标宽度:-1" frames/frame_%04d.png
```

先用 `ffprobe` 查看原始帧率和总帧数，按原始帧率提取，不丢帧。

## 2. 识别方向

用多模态模型逐帧标注朝向，分两步：

**粗识别**：4-10 fps 采样 → 识别方向 + 大致帧范围

**精确定位**：过渡区域逐帧 → 精确起止帧，标记 `turning` 排除

```
front: frame 1-72
turning: frame 73-97
right: frame 98-168
```

## 3. 确定帧数（短板原则）

各方向纯帧数的最小值 = 瓶颈帧数 N，所有方向统一取前 N 帧。

## 4. 识别脚步关键帧（保守策略）

**核心原则：宁可少帧，不要转身帧。**

一个完整跨步周期 = 6 帧：

| 帧序 | 姿态 | 说明 |
|------|------|------|
| 1 | left contact | 左脚踏地 |
| 2 | left mid | 左脚经过身体正下方 |
| 3 | left behind | 左脚在身后 |
| 4 | right contact | 右脚踏地 |
| 5 | right mid | 右脚经过身体正下方 |
| 6 | right behind | 右脚在身后 |

## 5. 补全缺失方向

水平镜像补全反方向（right → left，left → right）。

## 6. 抠图（绿幕 GrabCut）

```
video.mov → 帧提取(128px) → HSV绿色检测 → GrabCut → 合成 → 64px WebP
```

关键代码：
```python
def green_screen_cutout(img_rgb):
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    green_mask = cv2.inRange(hsv, [35,50,50], [85,255,255])
    gc_mask = np.zeros(hsv.shape[:2], np.uint8)
    gc_mask[green_mask > 0] = cv2.GC_BGD
    gc_mask[green_mask == 0] = cv2.GC_PR_FGD
    cv2.grabCut(img_rgb, gc_mask, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
    return alpha
```

**必须**：128px 处理 → 缩放 64px。不做边缘腐蚀。不做亮绿补充。

## 7. 裁剪 + 拼合

取所有帧并集边界框 + padding → 统一裁剪 → 拼 sprite sheet

```
Row 0: Front  [L-contact][L-mid][L-behind][R-contact][R-mid][R-behind]
Row 1: Left   [...]
Row 2: Right  [...]
Row 3: Back   [...]
```

## 8. 导出

- `sprite_sheet.png` — 透明背景 PNG
- `preview.gif` — 逐帧预览（标注方向+姿态+进度条）

## 常见问题

| 问题 | 解决 |
|------|------|
| 方向不纯 | 收紧帧范围，排除 turning 帧 |
| 速度不一致 | 检查帧数是否相同 |
| 绿色杂边 | 128px 下 GrabCut + 确保绿幕 |
| 切掉细节 | 不腐蚀边缘，窄范围 HSV |
| 关键帧不准 | 只选中间帧，宁可少帧 |
| 转身帧混入 | 宁愿丢帧保证纯度 |

---
**Related references:** [gameplay](../reference/gameplay.md) · [asset-pipeline](../reference/asset-pipeline.md)
