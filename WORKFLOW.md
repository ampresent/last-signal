# LAST SIGNAL — 工作流文档

## 目录
- [项目概览](#项目概览)
- [AI 图片生成 (Pollinations.AI)](#ai-图片生成)
- [AI 动画帧生成](#ai-动画帧生成)
- [实时光照系统](#实时光照系统)
- [光照编辑器](#光照编辑器)
- [对话系统](#对话系统)
- [角色行走系统](#角色行走系统)
- [Sprite Sheet 生成工作流（视频→sprite sheet）](#sprite-sheet-生成工作流视频sprite-sheet)
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
| 动画系统 | Depth Lighting (深度光照) + VFX 粒子引擎 + 视频→Sprite Sheet 角色动画 |
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
python3 gen_masks.py               # 3. MobileSAM + Omni 生成 mask (含叠层验证)
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
python3 gen_masks.py                       # 3. MobileSAM + Omni mask 生成 (含验证)
```

Canvas 粒子系统，在 AI 帧之上叠加实时效果。60fps，零额外文件体积。

**效果类型：**
| 效果 | 描述 | 场景 |
|---|---|---|
| 雨滴 | 倾斜雨丝粒子，支持风向；室内场景裁剪到窗口 mask | 街道/小巷/楼顶/公寓 |
| 雨滴溅起 | 雨滴碰硬表面（深度图检测）→ 飞溅小水滴粒子 | 有雨 + 深度图的场景 |
| 雨滴涟漪 | 雨滴落水面（water mask 检测）→ 同心圆波纹扩散 | 有水面的场景 |
| 雾气 | 径向渐变雾层，缓慢漂移 | 街道/楼顶/酒吧 |
| 霓虹脉冲 | 绿/紫光晕呼吸叠加 | 全场景 |
| 环境粒子 | 灰尘/蒸汽/烟雾/数据流/水滴/风尘 | 按场景区分 |
| 水面反射 | 场景反射 + 波纹扰动 + 镜面高光 + 涟漪（定位用 water mask） | 街道/小巷/塔楼/楼顶 |
| CRT 扫描线 | 滚动细线 | 公寓/酒吧/服务器室 |
| 全局闪烁 | 随机亮度抖动 | 除楼顶外 |
| 故障效果 | 偶发水平位移+红蓝色偏 | 全场景（低概率） |

**配置：** `VFX.SCENE_CONFIG` 中每个场景独立定义效果组合和参数。

**渲染顺序：** 雨滴（含溅起/涟漪） → 雾气 → 霓虹脉冲 → 环境粒子 → 水洼反射 → 暗角 → 闪烁 → 扫描线 → 故障

**雨滴碰撞系统：**
- **硬表面溅起**：采样深度图，当前像素与上方 6px 深度差 > 0.06 → 生成 3~5 个飞溅粒子（重力 + 淡出）
- **水面涟漪**：采样 water mask，雨滴落在白色区域 → 同心圆扩散（2~3 圈，600~900ms）
- 两者互斥，优先检测水面

**室内雨滴裁剪：**
- 室外场景（street/alley/tower/rooftop）：全屏雨滴
- 室内场景（apartment）：雨滴只在窗口 mask 区域内显示
- 实现方式：临时 canvas 画雨丝 → `destination-in` 用 mask 裁剪 → `drawImage` 叠加到主 canvas
- 配置：`rain: { ..., clipToMask: 'apartment_window' }`（mask 格式：`{sceneId}_{objId}`）

---

## 实时光照系统

基于 WebGL 的逐像素深度光照渲染器，替代预渲染帧序列，实现实时动态光照。

### 架构

```
lighting-engine.js   — WebGL 光照引擎（独立模块）
lighting-config.json  — 各场景光源配置
lighting-editor.html  — 可视化编辑器（开发用）
index.html            — 游戏主文件（加载引擎 + 配置）
```

### 光源类型

| 类型 | 说明 | 用途 |
|------|------|------|
| `point` | 点光源，有位置和半径 | 霓虹灯、台灯、屏幕光 |
| `directional` | 方向光，平行光线 | 月光、车灯 |
| `global` | 全局光，无方向 | 闪电、环境脉冲 |

### 光源参数

| 参数 | 说明 |
|------|------|
| `x, y` | 归一化坐标 (0-1) |
| `color` | RGB 颜色 `[r, g, b]` |
| `radius` | 点光源衰减半径 |
| `intensity` | 亮度强度 |
| `depth` | 光源 Z 深度 (0=near, 1=far) |
| `dir` | 方向光方向向量 `[dx, dy]` |
| `phase` | 动画相位函数 |
| `noise` | 随机噪声控制 |

### 相位动画系统

| 类型 | 说明 |
|------|------|
| `sine` | 正弦波呼吸 |
| `pulse` | 脉冲（可配速度/min/max） |
| `flicker` | 不规则闪烁（霓虹灯） |
| `car_sweep` | 车灯扫过相位 |
| `lightning` | 闪电（大部分时间暗，峰值闪亮） |
| `burst` | 突发闪烁 |
| `steady` | 恒定 |

### 噪声系统

每个光源可叠加随机噪声，产生有机、非机械的光照行为：

| 参数 | 说明 |
|------|------|
| `noise.intensity` | 噪声幅度 (0=关闭) |
| `noise.speed` | 噪声变化速度 |
| `noise.phase` | 噪声相位偏移 |

### 深度遮挡（Shadow Ray Marching）

逐像素从表面向光源投射阴影射线，64 步采样：

- 跟踪路径上最浅表面
- 比最浅表面更深的区域被遮挡
- 持续变浅的区域不遮挡（光能穿过浅区照亮更浅处）
- 详见 `gen_depth_lighting.py` → `ray_march_shadows()`

**深度衰减（实时点光源）— 几何锥体模型：**
- 光源有 XYZ 位置（x, y = 屏幕坐标，z = 深度值 0~1）
- 像素深度 ≤ 光源深度：100% 亮度（在光源前方）
- 像素深度 > 光源深度：根据**仰角**判断是否在光照锥内
  - `仰角 = atan(深度差 × 半径, 水平距离)`
  - `锥角 = 0.4 + 0.3 × clamp(半径/400, 0, 1)`（半径越大锥角越宽）
  - 仰角 < 锥角 → 照亮；超出 → smoothstep 渐变衰减
  - 附加距离衰减：`1/(1 + height²×8)`，深处指数衰减
- 效果：大半径光源（如 distant_warm r=550）照亮大范围前景，小半径光源（如 emergency r=270）照亮范围窄
- 每个光源根据自身 XYZ + 半径自动计算能照亮多少前景，无固定值

### 配置文件格式

```json
{
  "version": "1.0",
  "canvas": { "width": 960, "height": 640 },
  "ambient": 0.02,
  "scenes": {
    "scene_id": {
      "name": "场景名称",
      "base": "bg_scene.png",
      "depth": "scene_depth.png",
      "lights": [ ... ]
    }
  }
}
```

### 运行

```javascript
// 在 index.html 中
const engine = new LightingEngine(canvas, config);
engine.setScene('apartment');
engine.start();
```

---

## 光照编辑器

可视化光照参数编辑器（`lighting-editor.html`），用于实时调试光源。

### 功能

| 功能 | 说明 |
|------|------|
| 滑块控件 | 对数曲线（gamma 2.2），适合宽范围参数 |
| 3D Gizmo | 画布上直接拖拽光源位置（红=X, 绿=Y, 蓝=Z, Shift+拖拽=Z） |
| 吸色器 | 从渲染画布采样颜色 |
| 深度地图叠加 | D 键或 🗺️ 按钮切换深度可视化 |
| 自动深度采样 | 📍自动 按钮，点光源放置/拖拽时自动读取深度图 |
| 坐标叠加 | 显示光标位置 + 该点深度值 |
| CORS 安全保存 | 画布导出为 PNG（preserveDrawingBuffer） |
| 随机化 | 一键随机化选中光源参数 |
| 深度/强度范围 | 已扩展到 [0, 1] 全范围 |

### 快捷键

| 键 | 功能 |
|----|------|
| `D` | 切换深度地图叠加 |
| `Shift+拖拽` | 3D Gizmo Z 轴移动 |
| `Delete` | 删除选中光源 |

### 工作流

1. 打开 `lighting-editor.html`
2. 选择场景
3. 点击画布放置光源，或从列表选择现有光源
4. 用滑块调整参数（颜色、强度、半径、相位、噪声）
5. 用 3D Gizmo 直接在画布上拖拽位置
6. 点击 💾 保存到 `lighting-config.json`

---

## 对话系统

### 核心 API

```javascript
// 基础对话
await Game.showDialogue("说话者", "文本内容");

// 带选项的对话
const choice = await Game.showDialogue("说话者", "文本", [
  { text: "选项1", action: () => { ... } },
  { text: "选项2", action: () => { ... } },
]);

// 带表情的对话（自动切换头像）
await Game.showDialogue("Joker", "……", { expression: "angry" });

// 闲聊对话（非主线，可重复触发）
await Game.showCasualChat("说话者", "文本", { expression: "happy" });
```

### 表情系统

3 角色 × 6 表情 = 18 张 img2img 表情变体（Pollinations.AI 生成）。

| 角色 | 表情 |
|------|------|
| Joker | neutral, happy, angry, sad, surprised, thinking |
| Kai | neutral, happy, angry, sad, surprised, thinking |
| Oracle | neutral, happy, angry, sad, surprised, thinking |

表情图片：`assets/expressions/{character}_{expression}.png`

### 闲聊热点

非主线对话，分布在各场景可交互物体上：

| 场景 | 热点 | 触发方式 |
|------|------|----------|
| 公寓 | 收音机 | 点击 |
| 街道 | 拉面摊 | 点击 |
| 酒吧 | 点唱机 | 点击 |
| 小巷 | 流浪猫 | 点击 |
| 塔楼 | 玻璃碎片 | 点击 |

---

## 角色行走系统

### 架构

```
CharacterSystem       — 角色管理（加载、渲染、碰撞）
gen_character_views.py — 角色视角生成（视频→sprite sheet，统一管线）
gen_walk_masks.py     — 可行走区域 mask 生成
```

### 生成流程（视频→Sprite Sheet）

**核心思路：用 AI 平台生成各方向角色行走视频，再通过帧提取、方向识别、关键帧选取、MobileSAM mask 抠图，最终拼合成 sprite sheet。**

> 旧方案（img2img 逐帧生成）已废弃。当前唯一推荐流程见下方 [Sprite Sheet 生成工作流](#sprite-sheet-生成工作流视频sprite-sheet)。

```bash
# 完整流程（视频→sprite sheet + mask 抠图）
python3 gen_character_views.py              # 全部角色
python3 gen_character_views.py --char joker # 单个角色
```

### 角色数据

3 角色 × 4 方向 × 6 帧 = 72 张行走帧 PNG。

| 角色 | 文件名 |
|------|--------|
| Joker | `joker_{dir}_f{0-5}.png` |
| Kai | `kai_{dir}_f{0-5}.png` |
| Oracle | `oracle_{dir}_f{0-5}.png` |

Sprite Sheet：`sheet_{character}_{direction}.png`（6 帧水平排列）

### 移动方式

- **点击移动**：点击场景中可行走区域，角色自动寻路
- **键盘移动**：WASD / 方向键，8 方向移动
- **深度排序**：角色根据 Y 坐标（深度）自动排序渲染，实现前后遮挡

### 碰撞检测

- 使用 `masks/{scene}_walkable_mask.png` 判定可行走区域
- 白色 (>128) = 可行走，黑色 = 不可行走
- 角色移动时实时检测目标点是否在可行走区域内

### 可行走 Mask 生成

```bash
python3 gen_walk_masks.py              # 所有场景
python3 gen_walk_masks.py --scene bar  # 单个场景
```

输出：`assets/masks/{scene}_walkable_mask.png`

---

## Sprite Sheet 生成工作流（视频→sprite sheet）

将角色行走视频转换为带方向的 sprite sheet。这是角色动画素材的**唯一生成管线**。

### 0. 素材准备：生成方向视频（必须先完成）

> ⚠️ 在执行后续步骤之前，需要先在 AI 平台生成各方向的角色行走视频。

**推荐平台：** 豆包（字节跳动）、即梦 APP（字节跳动）

**生成流程：**

1. **生成角色正面图** — 在 AI 平台用文生图生成角色正面立绘
2. **图生图生成四个方向图** — 以正面图为基础，用图生图分别生成 front / back / left / right 四个方向的角色图
3. **方向图生视频** — 对每个方向的图，使用以下提示词生成行走视频：

```
生成视频：朝他面向的方向走路，作为标准素材使用，镜头保持角色在正中央，单镜头
```

**关键要求：**
- 镜头固定，角色保持在画面正中央
- 单镜头，不要切换
- 背景尽量纯色/均匀，方便后续抠图
- 每个方向单独生成一个视频文件

**生成完毕后，将视频文件命名为 `{character}_{direction}.mov`，例如：**
```
joker_front.mov
joker_back.mov
joker_left.mov
joker_right.mov
```

然后继续下面的步骤。

### 1. 提取帧

```bash
ffmpeg -y -i input.mov -vf "scale=目标宽度:-1" frames/frame_%04d.png
```

先用 `ffprobe` 查看原始帧率和总帧数，按原始帧率提取，不丢帧。

### 2. 识别方向

用多模态模型逐帧标注朝向。分两步：

**第一步：粗识别（低帧率采样）**

以 4-10 fps 采样送入模型，识别视频中出现了哪些方向、大致帧范围。

```
模型输入：视频 + prompt "逐帧标注角色朝向：front/right/back/left/turning"
模型输出：各方向的帧范围
```

**第二步：精确定位过渡帧**

在第一步识别出的过渡区域，逐帧（或每 2 帧）送入模型，精确定位：

- 每个纯方向的**起始帧**和**结束帧**
- 标记 `turning`（转身中）的帧全部排除

输出格式示例：

```
front: frame 1-72
turning: frame 73-97
right: frame 98-168
turning: frame 169-193
back: frame 194-241
```

**注意**：
- 模型判断不一定准，需要通过预览 GIF 人工复核
- 如果方向不纯，回头收紧帧范围再试
- 可能需要多轮迭代

### 3. 确定帧数（短板原则）

```
各方向纯帧数的最小值 = 瓶颈帧数 N
所有方向统一取前 N 帧（从各自纯帧范围的起始帧开始）
```

- 不抽帧、不跳帧 → 各方向播放速度一致
- 如果某方向帧数远多于瓶颈，可考虑裁掉尾部多余的行走周期

### 4. 识别脚步关键帧（保守策略）

**核心原则：宁可少帧，不要转身帧。**

不需要把瓶颈帧数全部用完。只需要一个完整跨步周期的关键帧即可。

**识别方法**：在每个方向的纯帧中间区域（远离转身），用模型逐帧判断脚步状态：

```
模型输入：纯方向中间区域的帧号列表
模型 prompt："判断角色脚步状态：left（左脚跨步）/ right（右脚跨步）/ mid（双脚并拢过渡）"
```

**一个完整跨步周期 = 6 帧**：

| 帧序 | 姿态 | 说明 |
|---|---|---|
| 1 | left contact | 左脚踏地 |
| 2 | left mid | 左脚经过身体正下方 |
| 3 | left behind | 左脚在身后 |
| 4 | right contact | 右脚踏地 |
| 5 | right mid | 右脚经过身体正下方 |
| 6 | right behind | 右脚在身后 |

从每个方向的纯帧中，找到这 6 个关键姿态对应的帧号。

**保守选帧规则**：
- 只选离转身区域最远的那一个跨步周期
- 如果某个方向的纯帧很少，可以只取 4 帧（contact + mid 各一次）
- 如果关键帧判断不准，宁可丢掉该方向，不要混入转身帧

### 5. 补全缺失方向

视频通常只拍角色一个侧身。需要**水平镜像**补全反方向：

```
原始侧身帧 → 水平翻转 → 对侧方向
```

常见情况：
- 只有 right → 镜像得到 left
- 只有 left → 镜像得到 right
- front / back 通常不需要镜像

### 6. 抠图（去背景）

#### 方案: 颜色距离抠图

从 sprite sheet 逐帧提取角色 cutout。用颜色距离区分角色和背景——角色颜色与背景差异大，距离阈值即可分离。

**原理：**

sprite sheet 的 alpha 只遮了外边框（~10%），alpha=255 区域里包含大量白/灰背景（~65%）和角色（~35%）。需要从 alpha=255 区域中把角色抠出来。

```
sheet_kai_{dir}.webp (sprite sheet, RGBA)
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 1: 拆帧                         │
  │   检测 alpha 列间隙 → 逐帧裁切       │
  │   连续 strip → 按 64px 等宽切分       │
  │   → 8 帧 × 64×128 RGBA              │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 2: 颜色距离抠图                  │
  │   从上边缘 (前5行) 采样背景色          │
  │   每个像素与背景色的欧氏距离           │
  │   dist > threshold → 前景             │
  │   形态学开/闭运算清理                  │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 3: 合成 RGBA + 清零背景 RGB      │
  │   alpha = 前景 mask (0/255)           │
  │   alpha=0 的像素 RGB 清零             │
  │   → PNG 输出                          │
  └─────────────────────────────────────┘
       │
       ▼
  输出: assets/sprites/cutout_kai_{dir}_f{0-7}.png
```

**Python 实现：**

```python
import cv2
import numpy as np

def color_cutout(frame_rgba, bg_color, threshold=20):
    """
    颜色距离抠图。
    frame_rgba: PIL RGBA Image (单帧)
    bg_color: 背景色 (float32 array, 从上边缘采样)
    threshold: 颜色距离阈值
    """
    arr = np.array(frame_rgba)
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]

    # 颜色距离
    dist = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))

    # 前景 = alpha=255 且颜色远离背景色
    fg_mask = ((alpha == 255) & (dist > threshold)).astype(np.uint8) * 255

    # 形态学清理
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    return fg_mask
```

**使用：**

```bash
python3 cutout_from_sheet.py --char kai          # 全部方向
python3 cutout_from_sheet.py --char kai --dir down  # 单方向
python3 cutout_from_sheet.py --char kai --threshold 25  # 调整阈值
```

**注意：**
- 不用 WebP：libwebp 会恢复 alpha=0 像素的 RGB，导致白边。用 PNG。
- 不用 MobileSAM/GrabCut：帧太小（64×128），SAM 返回全前景，GrabCut 反而扩大前景。颜色距离阈值更可控。

### 7. 裁剪 + 拼合

```python
# 1. 遍历所有帧，统计角色像素的边界框
# 2. 取所有帧的并集边界框，加少量 padding
# 3. 统一裁剪
# 4. 拼成 sprite sheet：行 = 方向，列 = 帧序号
```

布局：

```
Row 0: Front   [L-contact] [L-mid] [L-behind] [R-contact] [R-mid] [R-behind]
Row 1: Left    [L-contact] [L-mid] [L-behind] [R-contact] [R-mid] [R-behind]
Row 2: Right   [L-contact] [L-mid] [L-behind] [R-contact] [R-mid] [R-behind]
Row 3: Back    [L-contact] [L-mid] [L-behind] [R-contact] [R-mid] [R-behind]
```

缺少的方向跳过该行。

### 8. 导出

- **sprite_sheet.png** — 透明背景 PNG，供引擎使用
- **preview.gif** — 逐帧预览，每帧标注方向名 + 姿态名 + 进度条，方向切换处加分隔线，用于人工校验

### 常见问题

| 问题 | 解决 |
|---|---|
| 方向不纯（含转身帧） | 收紧帧范围，排除 turning 帧 |
| 各方向速度不一致 | 检查是否用了相同帧数，是否抽帧了 |
| 抠图残留背景 | 调整形态学 kernel 大小或增加 GrabCut 迭代次数；确保 MobileSAM mask 覆盖完整 |
| 镜像方向看起来不对 | 确认镜像的是正确方向（通常镜像侧身即可） |
| sprite sheet 尺寸过大 | 降低单帧分辨率（ffmpeg scale）或减少帧数 |
| 关键帧判断不准 | 只选纯方向最中间的帧，远离转身区；宁可少帧 |
| 转身帧混入 | 宁愿丢帧也要保证纯度，一个转身帧会毁掉整个方向 |

---

## 游戏引擎架构

### 文件结构
```
last-signal/
├── index.html              # 游戏主文件（HTML + CSS + JS 全内联）
├── lighting-engine.js      # WebGL 光照引擎
├── lighting-config.json    # 各场景光源配置
├── lighting-editor.html    # 可视化光照编辑器
├── gen_assets.py           # 素材生成（Pollinations.AI 文生图 + 角色肖像）
├── gen_depth_lighting.py   # Depth Lighting 渲染器（所有场景，HF 镜像 + 本地推理）
├── gen_masks.py            # MobileSAM + Omni mask 生成器（交互/可行走/水面 + 叠层验证）
├── gen_character_views.py   # 角色视角生成（视频→sprite sheet + MobileSAM mask 抠图）
├── gen_walk_preview.py     # 行走 GIF 预览生成器（4方向×6帧）
├── WORKFLOW.md             # 本文档
├── SETUP.md                # 环境搭建指南
├── DEVLOG.md               # 开发日志
└── assets/
    ├── bg_*_f0~f11.png     # 每场景 12 帧动画（Depth Lighting）
    ├── *_depth.png          # 各场景深度图缓存
    ├── portrait_*.png       # 角色肖像
    ├── expressions/         # 角色表情变体（3角色×6表情）
    ├── sprites/
    │   ├── cutout_{char}_{dir}.png    # 角色抠图
    │   ├── raw_{char}_{dir}.png       # 原始角色图
    │   ├── sheet_{char}_{dir}.png     # Sprite Sheet（8帧）
    │   └── {char}_{dir}_f{0-5}.png    # 逐帧 PNG
    └── masks/
        ├── {scene}_mask.png           # 组合 mask（交互区域并集）
        ├── {scene}_{obj}_mask.png     # 单独物体 mask
        ├── {scene}_walkable_mask.png  # 可行走区域 mask
        ├── {scene}_water_mask.png     # 水面区域 mask
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

**统一 mask 管线**：MobileSAM (ONNX) 精确分割 + Omni 视觉模型引导 + 叠层验证。

### 技术栈

| 组件 | 用途 | 说明 |
|------|------|------|
| MobileSAM (ONNX) | 精确分割 | encoder (27MB) + decoder (16MB), ONNX Runtime, 无需 GPU |
| mimo-omni | 物体识别 + mask 验证 | 多模态视觉模型, 识别 bbox + 审查 mask 质量 |

> **严格模式**: 无降级策略。模型缺失直接报错退出，不回退到 GrabCut。

### Mask 类型

| 类型 | 文件名 | 用途 |
|------|--------|------|
| 组合 mask | `{scene}_mask.png` | 所有可交互区域的并集，悬停检测 |
| 物体 mask | `{scene}_{obj}_mask.png` | 单个物体的精确 mask，点击归属 |
| 可行走 mask | `{scene}_walkable_mask.png` | 角色可行走区域，路径规划 |
| 水面 mask | `{scene}_water_mask.png` | 水面区域，反射 + 雨滴涟漪 |

白色 (>128) = 有效区域，黑色 = 背景。

### 生成流程 (三步流水线)

```
bg_{scene}.png (场景原图)
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 1: Omni 物体识别               │
  │   mimo-omni 分析场景图               │
  │   → 识别可交互物体 + 边界框 bbox     │
  │   (已有 bbox 定义时可跳过)           │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 2: MobileSAM 精确分割           │
  │   TinyViT encoder → image embedding │
  │   bbox prompt → mask decoder         │
  │   → 精确二值 mask (非矩形)           │
  │   + 形态学清理 (close/open)          │
  │   + 质量检查 (面积比 0.05%~35%)      │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ Step 3: 叠层验证 (Layer Verification)│
  │   将 mask 半透明叠加到原图           │
  │   Omni 审查:                        │
  │   ✓ mask 是否准确覆盖目标物体?       │
  │   ✓ mask 是否包含过多背景?           │
  │   ✓ mask 是否遗漏物体重要部分?       │
  │   → PASS / FAIL + 原因              │
  └─────────────────────────────────────┘
       │
       ▼
  输出: assets/masks/{scene}_{obj}_mask.png
        assets/masks/{scene}_mask.png (组合)
        assets/masks/{scene}_walkable_mask.png
        assets/masks/{scene}_water_mask.png
```

### 运行

```bash
# 完整流程 (所有场景, Omni 识别 + MobileSAM + 验证 + push)
python3 gen_masks.py

# 跳过 Omni 识别 (直接用 SCENES 中预定义的 bbox)
python3 gen_masks.py --skip-omni-detect

# 跳过叠层验证
python3 gen_masks.py --skip-verify

# 不自动 push
python3 gen_masks.py --no-push

# 单个场景
python3 gen_masks.py --scene apartment

# 组合: 单场景 + 跳过验证 + 不 push
python3 gen_masks.py --scene bar --skip-verify --no-push
```

### 场景配置 (gen_masks.py SCENES)

每个场景定义 `spawn`、`walkable` 和 `water` 字段：
```python
"street": {
    "spawn": [0.48, 0.64],  # 角色初始位置 (归一化坐标, 从 walkable mask 选取)
    "objects": [...],
    "walkable": {"bbox": [30, 160, 930, 627], "label": "街道地面"},
    "water": {"bbox": [30, 480, 930, 627], "label": "路面积水"},
    "edge_transitions": [...]
}
```
- `spawn`: 归一化坐标 `[x, y]` (0~1), 角色进入场景时的初始位置
- `water: None` 表示该场景无水面
- spawn 位置从 walkable mask 中自动采样中心区域, 确保角色站在可行走区域

### 依赖

| 依赖 | 大小 | 用途 |
|------|------|------|
| `onnxruntime` | ~15MB | MobileSAM ONNX 推理引擎 |
| `opencv-python-headless` | ~30MB | 图像处理 |
| `pillow` | ~3MB | 图片读写 |
| `numpy` | ~30MB | 数值计算 |
| `mobilesam.encoder.onnx` | 27MB | MobileSAM 图像编码器 (R2 下载) |
| `mobile_sam.onnx` | 16MB | MobileSAM mask 解码器 (R2 下载) |

### 模型下载

模型存放在 `models/` 目录，通过 R2 加速下载 (国内快):
```bash
bash setup.sh   # 自动从 R2 下载 encoder + decoder
```
首次运行 `gen_masks.py` 时如果模型不存在，会报错提示运行 `setup.sh`。

### 运行时使用

- **交互检测**：`Game.isMaskHit(x, y)` + `Game.objMasks[key]`
- **行走碰撞**：`CharSystem.isWalkable(nx, ny)` 读取 walkable mask
- **水面反射**：`Game.waterMasks[sceneId]` 定位水面 Y 范围
- **雨滴涟漪**：雨滴落在 water mask 白色区域 → 同心圆涟漪
- **雨滴溅起**：雨滴碰到深度图深度跳变处 → 飞溅粒子

### 视觉反馈

- Mask 仅用于检测，不在 canvas 上绘制任何视觉效果
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
python3 gen_masks.py               # 3. MobileSAM + Omni mask 生成 (含叠层验证)
python3 gen_character_views.py     # 4. 角色行走 sprite sheet（视频→帧提取→mask 抠图）
python3 gen_walk_preview.py        # 5. 行走 GIF 预览
```

### 添加新场景
1. `gen_assets.py` 添加 prompt
2. `gen_depth_lighting.py` 的 `SCENE_LIGHTS` 添加光源配置（位置/颜色/半径/相位函数）
3. `lighting-config.json` 添加实时渲染光源配置
4. `gen_masks.py` 添加物体 bbox + `walkable` + `water` 字段
5. `index.html` SCENES 添加场景定义
6. `VFX.SCENE_CONFIG` 添加动效配置（含 `puddleReflection` 如有水面）
7. 运行生成脚本
8. `git add -A && git commit && git push`

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

### 7. MobileSAM ONNX encoder 输入格式是 HWC 不是 NCHW

**现象**：`Invalid rank for input: input_image Got: 4 Expected: 3`
**原因**：PulpCut 导出的 MobileSAM encoder 期望 `[H, W, 3]` (HWC) 而非标准的 `[N, C, H, W]` (NCHW)
**解决**：预处理时 encoder 输入用 `normalized` (HWC float32), 不要 transpose 成 NCHW
```python
# ✗ 错误: tensor = normalized.transpose(2, 0, 1)[np.newaxis, ...]
# ✓ 正确: 直接传 normalized (shape [1024, 1024, 3])
```
decoder 的 `image_embeddings` 输入仍是 `[1, 256, 64, 64]` (4D)。

### 8. MobileSAM ONNX 模型需要 encoder + decoder 两个文件

**现象**：`External data path validation failed` 或推理结果全黑
**原因**：某些 HuggingFace 上的 MobileSAM ONNX 模型只有图结构, 权重在 `.data` 文件中未上传
**解决**：使用 PulpCut/mobilesam-onnx 的两个独立文件 (均已内嵌全部权重):
- `mobilesam.encoder.onnx` (27MB) — 图像编码器
- `mobile_sam.onnx` (16MB) — mask 解码器
存放于 R2 `s3://mystore/deps/`, `setup.sh` 自动下载。

### 9. Depth-Anything 深度图方向与游戏坐标系相反

**现象**：角色近处小、远处大 (近小远大)，缩放方向反了
**原因**：Depth-Anything 输出 white=near, black=far (白色=近处)。但游戏代码 `getDepth()` 直接返回 `pixel/255`，把 white 当成 far (1.0)，导致 `depthScale = 0.6 + (1.0-depth)*0.8` 计算出反向结果。
**解决**：`getDepth()` 返回 `1.0 - (pixel/255)` 取反，使 0=near, 1=far 与游戏坐标系一致。
```javascript
// ✗ 错误: return this.depthData.data[idx] / 255;
// ✓ 正确: return 1.0 - (this.depthData.data[idx] / 255);
```
> ⚠️ 注意：`gen_depth_lighting.py` 的光照渲染使用 `depth_factor = 1.0 - depth_float`，本身已处理了反转，不受影响。只有游戏引擎 `index.html` 的 `getDepth()` 需要修复。

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

## 图片格式规范

**所有生成的图片素材必须为 WebP 格式。** 不再允许生成 PNG、JPG、BMP 等其他格式的图片文件。

### 规则

- 生成脚本输出必须为 `.webp`（`ffmpeg -i input -quality 90 output.webp`）
- 如需从 PNG 转换：`ffmpeg -y -i input.png -quality 90 output.webp`
- `.gitignore` 已屏蔽 `.png`、`.jpg`、`.jpeg`、`.bmp`、`.gif` 等格式
- 例外：`preview_*.gif`（行走预览 GIF）允许保留

### 历史存量

`assets/masks/` 下 67 个同名 png+webp 文件已用 png 内容覆盖 webp（2026-04-26）。

---

*文档更新：2026-04-26*
*仓库：https://github.com/ampresent/last-signal*
*在线：https://ampresent.github.io/last-signal/*
