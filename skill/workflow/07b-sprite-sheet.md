# Sprite Sheet 生成工作流（视频→sprite sheet）

将角色行走视频转换为带方向的 sprite sheet。这是角色动画素材的**唯一生成管线**。

> **⚠️ 第零步：用视觉模型确认素材内容**
>
> 在任何处理之前，**必须先用多模态模型（omni）看一眼原始视频帧**，确认：
> 1. 角色外观和实际尺寸（全尺寸角色 vs 像素小人）
> 2. 背景类型（纯绿幕 / 自然草地 / 其他）
> 3. 角色在画面中的位置和占比
>
> **不要凭缩略图或文字描述猜测画面内容。** 错误的前提假设会导致整个流程走偏，
> 浪费大量时间在不匹配的算法参数上。3 秒的视觉确认可以省去 30 分钟的无效调试。
>
> ```bash
> # 提取一帧，用 omni 确认
> ffmpeg -y -i input.mov -vf "select=eq(n\,30)" -frames:v 1 check.png
> bash mimo_api.sh image check.png "描述图中角色的外观、尺寸、位置和背景类型"
> ```

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

## 6. 抠图（绿幕）

> **⚠️ 必须使用项目脚本 `greenscreen_cutout.py`，不要自己写 GrabCut。**
>
> GrabCut 在此场景下会侵蚀角色边缘。项目脚本使用纯 HSV 阈值移除绿色，
> 已经过 left/right/up 三个方向验证，自带 omni 模型自动验证循环。

### 6.1 裁剪角色区域（关键步骤）

**脚本要求输入是裁剪好的角色帧，不是全帧视频。** 直接传全帧会导致输出空文件
（512×910 贴到 64×128 画布上，什么都看不见）。

```python
# 从全帧中裁剪角色区域（用 omni 模型确认角色位置）
# 示例：角色在 720x1280 帧中大约 x=315-410, y=735-920
crop = frame[y1:y2, x1:x2]
Image.fromarray(crop).save(f'selected/frame_{idx:04d}.png')
```

### 6.2 运行抠图脚本

```bash
python3 greenscreen_cutout.py <direction> <cropped_frames_dir>

# 示例：
python3 greenscreen_cutout.py down down_selected
```

脚本自动流程：
1. 纯 HSV 绿色检测（H=35-85, S≥50, V≥50）
2. 逐帧用 omni 模型验证（无绿边 + 角色完整 + 背景透明）
3. 验证失败则自动扩大绿色范围重试（最多 5 轮）
4. 输出 `assets/sprites/{char}_{dir}_f{0-7}.webp`

### 6.3 如果脚本输出空文件

检查输入帧是否已裁剪到角色区域。脚本的 `process_frame` 直接将输入帧
贴到 64×128 画布，不做缩放——输入必须接近或小于 64×128。

**不做**：GrabCut、边缘腐蚀、亮绿补充、形态学开运算。

### 6.4 验证

提交前**必须**用 omni 模型检查至少一张输出：

```bash
bash mimo_api.sh image assets/sprites/kai_down_f0.webp \
  "角色可见吗？背景透明吗？边缘有绿边吗？简短回答。"
```

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
| 绿色杂边 | 提高 S/V 阈值（S≥70, V≥70） |
| 切掉细节 | 不腐蚀边缘，窄范围 HSV |
| 关键帧不准 | 只选中间帧，宁可少帧 |
| 转身帧混入 | 宁愿丢帧保证纯度 |
| **脚本输出空文件** | **输入帧必须先裁剪到角色区域，不能传全帧** |
| **GrabCut 吃边缘** | **不要用 GrabCut，用 `greenscreen_cutout.py`** |

---
**Related references:** [gameplay](../reference/gameplay.md) · [asset-pipeline](../reference/asset-pipeline.md)
