# LAST SIGNAL — 工作流文档

## 目录
- [项目概览](#项目概览)
- [AI 图片生成 (Pollinations.AI)](#ai-图片生成)
- [AI 动画帧生成](#ai-动画帧生成)
- [VFX 实时动效引擎](#vfx-实时动效引擎)
- [游戏引擎架构](#游戏引擎架构)
- [Mask 交互系统](#mask-交互系统)
- [素材生成流程](#素材生成流程)
- [部署到 GitHub Pages](#部署到-github-pages)
- [复用指南](#复用指南)

---

## 项目概览

| 项目 | 内容 |
|------|------|
| 游戏名 | LAST SIGNAL |
| 类型 | 2D Point & Click 冒险游戏 |
| 风格 | 赛博朋克 / 冷峻 noir |
| 技术栈 | 纯 HTML5 + Canvas + JavaScript（零依赖） |
| 图片生成 | Pollinations.AI（完全免费，无需 API Key） |
| 动画系统 | AI img2img 关键帧 + OpenCV 光流插值 + VFX 粒子引擎 |
| 部署 | GitHub Pages（静态托管） |

---

## AI 图片生成

### Pollinations.AI

完全免费，无需注册，无需 API Key，国内可用。

**文生图 (GET)：**
```
https://image.pollinations.ai/prompt/{提示词}?width=960&height=640&seed=2087&model=flux&nologo=true
```

**图生图 (POST)：**
```bash
curl -X POST \
  "https://image.pollinations.ai/prompt/{提示词}?width=960&height=640&seed=2087&model=flux&nologo=true" \
  -F "image=@base_image.png" \
  -o output.png
```
将 base image 作为 init image 输入，AI 在其基础上根据新提示词生成变体。

**参数：**
| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `prompt` | 提示词（URL 编码） | 越详细越好 |
| `width/height` | 尺寸 | 960×640（背景）/ 512×512（肖像） |
| `seed` | 随机种子 | `2087`（固定可复现） |
| `model` | 模型 | `flux` |
| `nologo` | 去水印 | `true` |

---

## AI 动画帧生成

### 策略：img2img 关键帧 + 光流插值

Pollinations 的 img2img 强度不可控（固定 diff≈25），直接用会产生帧间跳变。
解决方案：**只生成少量关键帧，用 OpenCV 光流在关键帧之间插值中间帧。**

**流程：**
1. 生成基础图 K0（文生图）
2. 用 img2img 生成 K1, K2, K3（微调提示词，控制场景变化方向）
3. OpenCV Farneback 光流在每对关键帧之间插值 2 个中间帧
4. 最后一帧 → 光流插值 → 回到第一帧 = 无缝循环

**输出：** 每场景 12 帧（f0-f11），文件名 `bg_{scene}_f{0-11}.png`

**帧间差异：**
- 原始 img2img：diff≈25（跳变明显）
- 光流插值后：diff 2-14（平滑渐变）
- 循环质量：首尾帧 diff≈3-5（无缝衔接）

### 运行

```bash
cd last-signal
python3 gen_ai_frames.py
# 8 场景 × 12 帧 = 96 帧，约需 10-15 分钟
```

### 场景动画剧本

每个场景有 4 个关键帧，描述一个完整循环：

| 场景 | K0 (基础) | K1 | K2 | K3 |
|------|----------|----|----|-----|
| apartment | 原始 | 终端微亮 | 雨变大 | 灯暗 |
| street | 原始 | 霓虹反射增强 | 暴雨+雾 | 街灯闪烁 |
| bar | 原始 | 紫红霓虹增强 | 烟雾变浓 | 灯光变暖 |
| alley | 原始 | 绿色霓虹增强 | 雨滴+蒸汽 | 霓虹熄灭 |
| tower | 原始 | 大厅灯微亮 | 雨势加大 | 一盏灯灭 |
| server | 原始 | LED 闪烁加快 | 屏幕变亮 | 日光灯闪烁 |
| rooftop | 原始 | 远景霓虹微亮 | 暴雨 | 闪电 |
| office | 原始 | 全息屏增强 | 窗上雨滴 | 台灯闪烁 |

---

## VFX 实时动效引擎

Canvas 粒子系统，在 AI 帧之上叠加实时效果。60fps，零额外文件体积。

**效果类型：**
| 效果 | 描述 | 场景 |
|---|---|---|
| 雨滴 | 倾斜雨丝粒子，支持风向；室内场景裁剪到窗口 mask | 街道/小巷/楼顶/公寓 |
| 雾气 | 径向渐变雾层，缓慢漂移 | 街道/楼顶/酒吧 |
| 霓虹脉冲 | 绿/紫光晕呼吸叠加 | 全场景 |
| 环境粒子 | 灰尘/蒸汽/烟雾/数据流/水滴/风尘 | 按场景区分 |
| 水洼反射 | 底部水面波纹 | 街道 |
| CRT 扫描线 | 滚动细线 | 公寓/酒吧/服务器室 |
| 全局闪烁 | 随机亮度抖动 | 除楼顶外 |
| 故障效果 | 偶发水平位移+红蓝色偏 | 全场景（低概率） |

**配置：** `VFX.SCENE_CONFIG` 中每个场景独立定义效果组合和参数。

**渲染顺序：** 雨滴 → 雾气 → 霓虹脉冲 → 环境粒子 → 水洼反射 → 暗角 → 闪烁 → 扫描线 → 故障

**室内雨滴裁剪：**
- 室外场景（street/alley/tower/rooftop）：全屏雨滴
- 室内场景（apartment）：雨滴只在窗口 mask 区域内显示
- 实现方式：临时 canvas 画雨丝 → `destination-in` 用 mask 裁剪 → `drawImage` 叠加到主 canvas
- 配置：`rain: { ..., clipToMask: 'apartment_window' }`（mask 格式：`{sceneId}_{objId}`）

---

## 游戏引擎架构

### 文件结构
```
last-signal/
├── index.html              # 游戏主文件（HTML + CSS + JS 全内联）
├── gen_assets.py           # 素材生成（Pollinations.AI 文生图 + 角色肖像）
├── gen_ai_frames.py        # AI 动画帧生成（img2img 关键帧 + 光流插值）
├── gen_anim_frames.py      # Legacy 动画帧（程序化图像效果，降级方案）
├── gen_masks.py            # GrabCut 精细 mask 生成器
├── WORKFLOW.md             # 本文档
└── assets/
    ├── bg_*_f0~f11.png     # 每场景 12 帧动画（AI + 光流插值）
    ├── portrait_*.png      # 角色肖像
    └── masks/
        ├── {scene}_mask.png           # 组合 mask
        ├── {scene}_{obj}_mask.png     # 单独物体 mask
        └── mask_metadata.json
```

### 核心模块

#### 1. Game 对象
```javascript
const Game = {
  canvas, ctx,           // Canvas 渲染
  currentScene,          // 当前场景 ID
  bgFrames: {},          // sceneName → [Image, Image, ...] 动画帧
  currentFrame,          // 当前帧索引
  frameTimer,            // 帧计时器
  frameInterval: 800,    // 帧间隔 ms
  inventory: [],         // 背包
  flags: {},             // 剧情标记
  masks, objMasks,       // Mask 数据
  _edgeCache,            // 预计算边缘像素
  _labelCache,           // 预计算标签位置
  _overlayCache,         // 预计算遮罩 canvas
};
```

#### 2. 场景系统
```javascript
{
  name: "场景名称",
  background: "bg_xxx",
  onEnter() {},          // 入场对话
  hotspots: [{           // 可点击区域
    x, y, w, h,          // 坐标（降级用）
    label: "▸ 提示",
    maskId: "obj_id",    // 对应 mask 文件
    condition() {},       // 显示条件
    action() {},          // 点击逻辑
  }]
}
```

#### 3. 渲染循环
```
loadImages() → loadMasks() → 预计算边缘/标签/遮罩
goScene(sceneId) → VFX.init(sceneId) → startRenderLoop()
  每帧 (~60fps):
    drawImage(bgFrames[currentFrame])  // AI 帧序列
    VFX.render(ctx, dt, sceneId)       // 粒子叠加
    draw pre-computed edges/overlay    // 热点高亮（零扫描）
```

#### 4. 性能优化
- **willReadFrequently: true** — 告诉浏览器用 CPU canvas 加速 getImageData
- **预计算 mask 数据** — 加载时算好边缘像素数组、标签中心、遮罩 canvas
- **render 零扫描** — 只需遍历预计算数组画点，不扫像素

#### 5. 对话系统
```javascript
await Game.showDialogue("说话者", "文本");
const choice = await Game.showDialogue("说话者", "文本", [
  { text: "选项1" }, { text: "选项2" },
]);
```

#### 6. 物品/音效系统
```javascript
Game.addItem("datachip");  Game.hasItem("datachip");
Game.sfx("click"|"pickup"|"door"|"error"|"success");
```

---

## Mask 交互系统

**二值 mask 图片**做像素级碰撞检测，替代矩形热区。

- 组合 mask `masks/{scene}_mask.png` — 悬停效果
- 单独 mask `masks/{scene}_{obj}_mask.png` — 点击归属
- 白色 (>128) = 可交互，黑色 = 背景

**生成流程：**
1. 视觉模型识别物体边界框 `[x1, y1, x2, y2]`
2. `gen_masks.py` 用 OpenCV GrabCut 精细分割
3. 输出非矩形精确 mask

**视觉反馈：**
- Mask 仅用于交互检测（悬停/点击），不在 canvas 上绘制任何视觉效果
- 光标在可交互区域变为 pointer，顶部显示 hint 文字
- VFX 雨滴可通过 `clipToMask` 裁剪到指定 mask 区域

---

## 素材生成流程

### 一键生成
```bash
python3 gen_assets.py          # 基础图 + AI 帧
python3 gen_assets.py --legacy # 基础图 + Legacy 帧（降级）
```

### 分步生成
```bash
python3 gen_assets.py          # 1. 生成基础场景图 + 角色肖像
python3 gen_ai_frames.py       # 2. AI img2img 关键帧 + 光流插值 (12帧/场景)
python3 gen_masks.py           # 3. 生成 mask（可选，已有则跳过）
```

### 添加新场景
1. `gen_assets.py` 添加 prompt
2. `gen_ai_frames.py` 添加关键帧配置
3. `gen_masks.py` 添加物体 bbox
4. `index.html` SCENES 添加场景定义
5. `VFX.SCENE_CONFIG` 添加动效配置
6. 运行 `python3 gen_assets.py && python3 gen_ai_frames.py`
7. `git add -A && git commit && git push`

---

## 部署到 GitHub Pages

```bash
git remote add origin https://github.com/用户/仓库名.git
git add . && git commit -m "init" && git push -u origin main
# GitHub → Settings → Pages → Deploy from branch → main → / (root)
```

更新：`git add -A && git commit -m "update" && git push`

---

## 复用指南

1. 写剧情大纲，列出场景/物品/角色
2. 修改 `gen_assets.py` 中的 PROMPTS + `gen_ai_frames.py` 中的关键帧配置
3. 复制引擎代码，在 `SCENES` 中定义场景
4. `python3 gen_assets.py && python3 gen_ai_frames.py`
5. 本地测试 `python3 -m http.server 8765`
6. 推送部署

---

*文档更新：2026-04-22*
*仓库：https://github.com/ampresent/last-signal*
*在线：https://ampresent.github.io/last-signal/*
