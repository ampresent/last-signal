# LAST SIGNAL — 工作流文档

## 目录
- [项目概览](#项目概览)
- [AI 图片生成 (Pollinations.AI)](#ai-图片生成)
- [AI 动画帧生成](#ai-动画帧生成)
- [VFX 实时动效引擎](#vfx-实时动效引擎)
- [游戏引擎架构](#游戏引擎架构)
- [Mask 交互系统](#mask-交互系统)
- [素材生成流程](#素材生成流程)
- [踩坑经验](#踩坑经验)
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
| 图片生成 | Pollinations.AI（完全免费，无需 API Key，国内可用） |
| 深度估计 | Depth-Anything-V2-Large（hf-mirror.com 下载 + 本地推理） |
| 动画系统 | Depth Lighting (深度光照) + VFX 粒子引擎 |
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

### 策略：Depth Lighting（所有场景统一）

所有场景统一使用 **Depth-Anything-V2-Large 深度估计 + 程序化 2D 光照渲染**：

```
bg_{scene}.png (基础图)
       │
       ▼
  hf-mirror.com 下载 Depth-Anything-V2-Large → 本地推理 → {scene}_depth.png
       │
       ▼
  每帧 (f0–f11):
    ├─ 定义 N 个光源参数（位置、颜色、强度、半径、相位函数）
    ├─ 逐像素计算光照
    │   ├─ 距离衰减 (inverse-square)
    │   ├─ 深度调制 (近面更亮)
    │   └─ 阴影光线步进 (64 steps, depth occlusion)
    ├─ 合成: base + lighting (additive blending)
    └─ 保存帧 PNG
```

**各场景光源配置（夜间最低级别光照）：**

| 场景 | 光源 | 效果 |
|------|------|------|
| apartment | 月光、车灯×2、屏幕×2 | 冷蓝月光 + 暖黄方向车灯平移穿过窗户（不穿墙、低强度） + CRT绿光闪烁 |
| street | 霓虹(品红/青)、车灯、积水反射 | 霓虹脉冲 + 车灯扫过 + 地面反射 |
| bar | 紫霓虹、红霓虹、吧台背光、电视 | 紫红呼吸 + 琥珀吧台 + 电视闪烁 |
| alley | 绿霓虹、应急灯、街灯漏光 | 霓虹闪烁 + 红色脉冲 + 远处暖光 |
| tower_exterior | 大厅灯光、玻璃反射、岗亭 | 暖光透出 + 冷色反射 + 恒定岗亭灯 |
| server_room | 蓝LED、绿LED、荧光灯、终端 | LED不规则闪烁 + 荧光灯抖动 + 终端绿光 |
| rooftop | 城市霓虹、闪电、天线灯 | 远处冷色辉光 + 闪电脉冲 + 红色天线灯 |
| office | 全息屏、台灯、窗外城市 | 蓝色全息闪烁 + 暖色台灯 + 冷色窗外 |

**相位函数：** 所有频率均为帧数整数倍，保证 f0 == f12 精确循环闭合。

**运行：**
```bash
# 设置 HF 镜像（首次运行前必须设置）
export HF_ENDPOINT=https://hf-mirror.com

# 完整流程（所有场景）
python3 gen_depth_lighting.py

# 单个场景
python3 gen_depth_lighting.py --scene apartment

# 仅重新渲染（复用已有深度图）
python3 gen_depth_lighting.py --lighting-only

# 仅生成深度图
python3 gen_depth_lighting.py --depth-only
```

**依赖：** `torch`, `transformers`, `timm`, `opencv-python-headless`, `numpy`
**深度模型：** Depth-Anything-V2-Large（从 hf-mirror.com 下载，本地 transformers pipeline 推理）
**输出：** `assets/{scene}_depth.png` + `assets/bg_{scene}_f0~f11.png`

### 运行顺序

```bash
cd last-signal

export HF_ENDPOINT=https://hf-mirror.com  # 设置 HF 镜像

python3 gen_assets.py              # 1. 基础场景图 + 角色肖像
python3 gen_depth_lighting.py      # 2. Depth Lighting (所有场景，自动跳过已有深度图)
python3 gen_masks.py               # 3. 生成 mask（可选，已有则跳过）
```

### 场景动画剧本

每个场景的光源通过相位函数控制亮度变化，形成自然的光照循环。

### 一键生成
```bash
export HF_ENDPOINT=https://hf-mirror.com
python3 gen_assets.py              # 基础图
python3 gen_depth_lighting.py      # 所有场景 Depth Lighting
```

### 分步生成
```bash
export HF_ENDPOINT=https://hf-mirror.com

python3 gen_assets.py                      # 1. 生成基础场景图 + 角色肖像
python3 gen_depth_lighting.py              # 2. 所有场景 Depth Lighting
python3 gen_depth_lighting.py --scene apartment  # 或只渲染单个场景
python3 gen_masks.py                       # 3. 生成 mask（可选）
```

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
├── gen_depth_lighting.py   # Depth Lighting 渲染器（所有场景，HF 镜像 + 本地推理）
├── gen_anim_frames.py      # Legacy 动画帧（程序化图像效果，降级方案）
├── gen_masks.py            # GrabCut 精细 mask 生成器
├── WORKFLOW.md             # 本文档
├── SETUP.md                # 环境搭建指南
├── DEVLOG.md               # 开发日志
└── assets/
    ├── bg_*_f0~f11.png     # 每场景 12 帧动画（Depth Lighting）
    ├── *_depth.png          # 各场景深度图缓存
    ├── portrait_*.png       # 角色肖像
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

### 分步生成（推荐顺序）
```bash
export HF_ENDPOINT=https://hf-mirror.com  # 设置 HF 镜像

python3 gen_assets.py              # 1. 生成基础场景图 + 角色肖像
python3 gen_depth_lighting.py      # 2. Depth Lighting (所有场景，自动跳过已有深度图)
python3 gen_masks.py               # 3. 生成 mask（可选，已有则跳过）
```

### 添加新场景
1. `gen_assets.py` 添加 prompt
2. `gen_depth_lighting.py` 的 `SCENE_LIGHTS` 添加光源配置（位置/颜色/半径/相位函数）
3. `gen_masks.py` 添加物体 bbox
4. `index.html` SCENES 添加场景定义
5. `VFX.SCENE_CONFIG` 添加动效配置
6. 运行生成脚本
7. `git add -A && git commit && git push`

---

## 踩坑经验

> 这些是从实战中总结的经验，避免重复踩坑。

### 1. HuggingFace 国内不可达

**现象**：`requests.ConnectionError: Failed to establish a new connection`
**原因**：阿里云 ECS 等国内服务器 DNS 解析 huggingface.co 到 Facebook IP，连接超时。
**解决**：使用 `hf-mirror.com` 下载模型，本地推理。
```bash
export HF_ENDPOINT=https://hf-mirror.com
```
> ⚠️ hf-mirror.com 只提供模型下载，不提供 Serverless Inference API。

### 2. torch `+cpu` 版本号导致 transformers 崩溃

**现象**：`TypeError: expected string or bytes-like object, got 'NoneType'`
**原因**：`importlib.metadata.version('torch')` 返回 `None`（dist-info 目录名含 `+cpu`）
**解决**：重命名 dist-info 目录 + 修复 METADATA 中的版本号（见 SETUP.md §3d）

### 3. torchvision stub 不完整

**现象**：`ModuleNotFoundError: No module named 'torchvision.io'` / `'torchvision.transforms.v2'`
**原因**：torchvision stub 只实现了 timm 需要的接口，transformers 5.x 额外依赖更多模块。
**解决**：手动补充 `io`、`v2` 模块 stub + `pil_to_tensor` + `NEAREST_EXACT` + `resize(antialias=)`（见 SETUP.md §3c）

### 4. ~~gen_ai_frames.py 覆盖公寓帧~~

> **已解决**：img2img 策略已完全移除，所有场景统一使用 Depth Lighting。
> 旧版 `gen_ai_frames.py` 已删除，不再需要担心帧覆盖问题。

### 5. s3cmd 必须 `--region=auto`

**现象**：`InvalidRegionName` 错误
**原因**：R2 默认区域名不是 AWS 标准区域名
**解决**：所有 s3cmd 命令加 `--region=auto`

### 6. pip 需要 `--break-system-packages`

**现象**：`externally-managed-environment` 错误
**原因**：Ubuntu 24.04 的 Python 被系统管理
**解决**：所有 pip 命令加 `--break-system-packages`

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
2. 修改 `gen_assets.py` 中的 PROMPTS
3. 在 `gen_depth_lighting.py` 的 `SCENE_LIGHTS` 中配置光源
4. 复制引擎代码，在 `SCENES` 中定义场景
5. 运行生成脚本
6. 本地测试 `python3 -m http.server 8765`
7. 推送部署

---

*文档更新：2026-04-23*
*仓库：https://github.com/ampresent/last-signal*
*在线：https://ampresent.github.io/last-signal/*
