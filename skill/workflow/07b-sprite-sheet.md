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

## 6. 抠图（RMBG-1.4）

> **使用 `scripts/rmbg14_cutout.py` 进行抠图。无需 HF token（公开模型）。**
>
> RMBG-1.4 使用深度学习模型移除背景，适用于任意背景（不限绿幕）。
> 支持单帧模式和 sheet 模式（sheet 快 7.5x）。

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
python3 scripts/rmbg14_cutout.py <direction> <cropped_frames_dir>

# 示例：
python3 scripts/rmbg14_cutout.py down down_selected
python3 scripts/rmbg14_cutout.py left left_selected --no-verify
python3 scripts/rmbg14_cutout.py up up_selected --sheet --no-verify  # sheet 模式更快
```

**前置依赖**：`torch` + `transformers` + `timm` + `kornia`（见 SETUP.md §3b）。
缺少任何一个都会导致 `ModuleNotFoundError` 或 `ImportError`。

**内存要求**：模型加载 + 推理峰值约 1.5-2GB。3.4GB 机器可行。

脚本自动流程：
1. 加载 RMBG-1.4 模型（本地 R2 副本，或从 hf-mirror.com 自动下载）
2. 逐帧推理（或 `--sheet` 整张推理），生成 alpha mask
3. 自动裁剪 + 缩放到 64×128 画布（80% 高度比，保留 13px head/foot margin）
4. 可选 omni 模型验证（默认开启，`--no-verify` 跳过）
5. 输出 `assets/sprites/{char}_{dir}_f{0-7}.webp`

### 6.3 如果脚本输出空文件

检查输入帧是否已裁剪到角色区域。脚本的 `process_frame` 直接将输入帧
贴到 64×128 画布，不做缩放——输入必须接近或小于 64×128。

### 6.4 验证

提交前**必须**用 omni 模型检查至少一张输出：

```bash
bash mimo_api.sh image assets/sprites/kai_down_f0.webp \
  "角色可见吗？背景透明吗？边缘有绿边吗？简短回答。"
```

### 6.5 抠图方案对比（逐帧 vs 拼 sheet）

在 3.4GB 内存 CPU 机器上实测（8帧 500×1100 → 64×128，80% 高度比），RMBG-1.4：

| 方案 | 耗时 | 说明 |
|------|------|------|
| A: 逐帧推理（8次） | 23.6s (3.0s/帧) | 稳定 |
| B: 拼 4×2 sheet 单次推理 | **3.2s (0.4s/帧)** | ✅ 推荐，快 7.5x |

**结论：Sheet 模式在 CPU 环境下显著更快。推荐使用 `--sheet` 参数。**

### 6.6 跨方向尺寸校对（必须）

不同方向的视频素材中，角色在画面里的占比往往不一致（常见：正面/背面比侧面小 15-20%）。
如果不校对，游戏里转向时角色会忽大忽小。

**检测方法：**

```python
from PIL import Image
import glob

for d in ['up', 'down', 'left', 'right']:
    files = sorted(glob.glob(f'assets/sprites/kai_{d}_f*.webp'))
    heights = []
    for f in files:
        img = Image.open(f).convert('RGBA')
        bbox = img.getbbox()
        if bbox:
            heights.append(bbox[3] - bbox[1])
    avg = sum(heights) / len(heights) if heights else 0
    print(f'{d}: avg content h={avg:.1f}px')
```

各方向平均内容高度差异 **>5%** 就需要校对。

**修复：**

```bash
python3 scripts/fix_sprite_scale.py
```

脚本逻辑：
1. 计算四个方向的平均角色内容高度
2. 取最大值作为目标高度
3. 对偏小的方向：提取内容 → 等比缩放到目标高度 → 居中贴回 64×128 画布
4. 差异 <5% 的方向不处理

校对后再做一次视觉验证，确认缩放没有引入模糊或变形。

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
| **头/脚被裁掉** | **缩放比太高。用 HEIGHT_RATIO=0.80，确保 13px+ margin（验证 rmin>0 且 rmax<127）** |
| 方向不纯 | 收紧帧范围，排除 turning 帧 |
| 速度不一致 | 检查帧数是否相同 |
| 关键帧不准 | 只选中间帧，宁可少帧 |
| 转身帧混入 | 宁愿丢帧保证纯度 |
| **脚本输出空文件** | **输入帧必须先裁剪到角色区域，不能传全帧** |
| **边缘有残留** | **检查 RMBG-1.4 模型是否加载成功，输入帧是否正确裁剪** |
| **转向时角色忽大忽小** | **各方向素材角色占比不同，必须做 6.6 跨方向尺寸校对** |

### ⚠️ Sprite 画布尺寸规范（防踩坑）

**问题**：64×128 画布太小，角色缩放到 128px 后 head/foot 紧贴甚至超出画布边缘。

**规范**：
- 画布尺寸：**64×128**（宽高比 1:2，游戏引擎依赖此比例）
- 缩放比：`HEIGHT_RATIO = 0.80`（角色占画布高度的 80%）
- 结果：角色高度 ≈ 102px，上下各有 ≈13px margin
- 验证：抠图后检查 `alpha` 通道，确保 `rmin > 0` 且 `rmax < 127`

**为什么不能贴边？**
- 游戏引擎中角色需要上下微调位置（跳跃、蹲下等动画）
- 贴边会导致 head/foot 在任何偏移下都被裁掉
- 14px margin 提供了足够的调整空间

---
**Related references:** [gameplay](../reference/gameplay.md) · [asset-pipeline](../reference/asset-pipeline.md)
