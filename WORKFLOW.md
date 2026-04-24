# LAST SIGNAL — 工作流文档

## 目录
- [项目概览](#项目概览)
- [AI 图片生成 (Pollinations.AI)](#ai-图片生成)
- [AI 动画帧生成](#ai-动画帧生成)
- [实时光照系统](#实时光照系统)
- [光照编辑器](#光照编辑器)
- [对话系统](#对话系统)
- [角色行走系统](#角色行走系统)
- [DragonBones 骨骼动画](#dragonbones-骨骼动画)
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
gen_character_views.py — 角色视角生成（正面→img2img 三角度）
gen_character_sprites.py — 旧版行走帧生成（已弃用，保留兼容）
gen_walk_masks.py     — 可行走区域 mask 生成
dragonbones_rig.py    — DragonBones 骨骼自动绑定
```

### 生成流程（v2：正面→img2img）

**核心思路：先生成高质量正面图，再用 img2img 保持角色一致性地生成其他角度。**

```bash
# Step 1: 生成角色正面 + img2img 其他角度
python3 gen_character_views.py              # 全部角色
python3 gen_character_views.py --char joker # 单个角色
python3 gen_character_views.py --front-only # 只生成正面

# Step 2: 骨骼绑定 + sprite sheet
python3 dragonbones_rig.py --batch
```

**流程图：**
```
text2img(Pollinations) → raw_{char}_down.png (正面)
       │
       ▼
cutout(rembg/fallback) → cutout_{char}_down.png (正面抠图)
       │
       ├──img2img(正面→左) → raw_{char}_left.png → cutout
       ├──img2img(正面→右) → raw_{char}_right.png → cutout
       └──img2img(正面→后) → raw_{char}_up.png   → cutout
       │
       ▼
dragonbones_rig.py → 4方向 × 8帧行走动画 + sprite sheet
```

**img2img 优势：** 角色外观、配色、服装在四个角度间保持一致，避免独立生成导致的角色"变脸"。

### 角色数据

3 角色 × 4 方向 × 8 帧 = 96 张行走帧 PNG。

| 角色 | 文件名 |
|------|--------|
| Joker | `joker_{dir}_f{0-7}.png` |
| Kai | `kai_{dir}_f{0-7}.png` |
| Oracle | `oracle_{dir}_f{0-7}.png` |

Sprite Sheet：`sheet_{character}_{direction}.png`（8 帧水平排列）

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

## DragonBones 骨骼动画

自动生成 DragonBones 格式骨骼 + 行走动画，用于替代逐帧手绘。

### 功能

1. **自动身体部位检测** — 从正面角色图识别头、躯干、左/右臂、左/右腿
2. **骨骼层级生成** — 12 节骨骼（root → hip → spine → head，四肢各 2 节）
3. **方向行走动画** — 4 方向各 8 帧（腿部摆动、手臂反向摆动、髋部弹动）
4. **Sprite Sheet 渲染** — 基于骨骼旋转的逐帧图像变形
5. **DragonBones JSON 导出** — `_ske.json` + `_tex.json`

### 使用

```bash
# 单个角色/方向
python3 dragonbones_rig.py assets/sprites/cutout_joker_down.png -o assets/rig_joker --preview

# 批量处理所有角色 × 所有方向
python3 dragonbones_rig.py --batch
```

### 输出

每个角色/方向生成：
- `sheet_{char}_{dir}.png` — 8 帧 sprite sheet
- `{char}_{dir}_f{0-7}.png` — 逐帧 PNG
- `rig_{char}_{dir}/` — DragonBones 骨骼数据
  - `{name}_ske.json` — 骨骼 + 动画数据
  - `{name}_tex.json` — 纹理图集
  - `{name}.png` — 角色图片

### 身体部位检测原理

使用 alpha 通道垂直投影分析：
- **颈部检测**：扫描上半身 45% 区域，找到行宽最小值（局部最小值 = 颈部）
- **头部**：顶部 → 颈部，使用 mask 像素确定宽度
- **躯干**：颈部 → 55% 高度处
- **手臂**：躯干边界外侧的像素区域
- **腿部**：下半身，通过中心间隙分割左右腿

### 骨骼层级

```
root
└── hip (髋部中心)
    ├── spine (躯干中心)
    │   ├── head (头部)
    │   ├── left_upper_arm → left_lower_arm
    │   └── right_upper_arm → right_lower_arm
    ├── left_upper_leg → left_lower_leg
    └── right_upper_leg → right_lower_leg
```

### 行走动画参数

**校准基准：** 以官方 DragonBones DragonBoy 开源数据 (`DragonBoy.json` → `walk` 动画) 为参考。
源仓库：`https://github.com/nicefairy/DragonBonesJS`

| 部位 | 当前值 | DragonBoy 官方 | 说明 |
|------|--------|---------------|------|
| 上腿 | ±45° | ±90°~±95° | 取半值，避免 2D cutout 过度变形 |
| 下腿 | ±55° | ±84°~±114° | 膝盖弯曲 |
| 上臂 | ±35° | ±51°~±120° | 肩部摆动 |
| 下臂 | ±25° | ±17°~±45° | 肘部屈伸 |
| 手 | ±20° | ±30°~±45° | 手腕摆动 |
| 髋部弹动 | 12px | 25px | 上下弹跳 |
| 脊柱 | ±8° | 隐含在 body | 身体摇摆 |
| 头部 | ±5° | ±10° | 反向稳定 |
| 缩放 | 1.0~1.06 | 1.0~1.14 | 近大远小 |

### 导入 DragonBones Pro

1. 打开 DragonBones Pro
2. 文件 → 导入 → 选择 `{name}_ske.json`
3. 自动加载骨骼 + 行走动画
4. 可继续编辑动画细节、添加 mesh 变形

### 行走 GIF 预览

```bash
python3 gen_walk_preview.py              # 所有角色
python3 gen_walk_preview.py --char kai   # 单个角色
```

输出 `assets/sprites/previews/{char}_walk.gif`：4 行（DOWN/LEFT/RIGHT/UP）× 8 帧行走动画。
用于快速验证骨骼绑定和动画效果是否正确。

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
├── gen_anim_frames.py      # Legacy 动画帧（程序化图像效果，降级方案）
├── gen_masks.py            # GrabCut 精细 mask 生成器（统一：交互/可行走/水面）
├── gen_character_views.py   # 角色视角生成（正面→img2img，推荐）
├── gen_character_sprites.py  # 旧版角色行走帧生成（已弃用，保留兼容）
├── gen_walk_preview.py     # 行走 GIF 预览生成器（4方向×8帧）
├── dragonbones_rig.py      # DragonBones 骨骼自动绑定 + sprite sheet 生成
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
    │   ├── {char}_{dir}_f{0-7}.png    # 逐帧 PNG
    │   └── rig_{char}_{dir}/          # DragonBones 骨骼数据
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

**统一 mask 管线**：所有 mask（交互、可行走、水面）都通过同一套视觉模型 + GrabCut 流程生成。

### Mask 类型

| 类型 | 文件名 | 用途 |
|------|--------|------|
| 组合 mask | `{scene}_mask.png` | 所有可交互区域的并集，悬停检测 |
| 物体 mask | `{scene}_{obj}_mask.png` | 单个物体的精确 mask，点击归属 |
| 可行走 mask | `{scene}_walkable_mask.png` | 角色可行走区域，路径规划 |
| 水面 mask | `{scene}_water_mask.png` | 水面区域，反射 + 雨滴涟漪 |

白色 (>128) = 有效区域，黑色 = 背景。

### 生成流程

`gen_masks.py` 统一处理所有 mask 类型：

1. 视觉模型识别物体边界框 `[x1, y1, x2, y2]`
2. GrabCut 精细分割每个物体 → `{scene}_{obj}_mask.png`
3. `walkable` 区域用 GrabCut 分割，自动减去物体 mask（障碍物）→ `{scene}_walkable_mask.png`
4. `water` 区域用 GrabCut 分割 → `{scene}_water_mask.png`
5. 组合所有物体 mask + 边缘过渡 → `{scene}_mask.png`

### 场景配置（gen_masks.py SCENES）

每个场景新增 `walkable` 和 `water` 字段：
```python
"street": {
    "objects": [...],
    "walkable": {"bbox": [30, 160, 930, 627], "label": "街道地面"},
    "water": {"bbox": [30, 480, 930, 627], "label": "路面积水"},
    "edge_transitions": [...]
}
```
`water: None` 表示该场景无水面。

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
python3 gen_masks.py               # 3. 生成统一 mask（交互/可行走/水面）
python3 dragonbones_rig.py --batch # 4. DragonBones 骨骼绑定
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

*文档更新：2026-04-24*
*仓库：https://github.com/ampresent/last-signal*
*在线：https://ampresent.github.io/last-signal/*
