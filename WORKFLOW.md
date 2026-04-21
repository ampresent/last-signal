# LAST SIGNAL — 工作流文档

## 目录
- [项目概览](#项目概览)
- [免费文生图工作流 (Pollinations.AI)](#免费文生图工作流)
- [游戏引擎架构](#游戏引擎架构)
- [素材生成流程](#素材生成流程)
- [部署到 GitHub Pages](#部署到-github-pages)
- [复用指南：如何制作新游戏](#复用指南)

---

## 项目概览

| 项目 | 内容 |
|------|------|
| 游戏名 | LAST SIGNAL |
| 类型 | 2D Point & Click 冒险游戏 |
| 风格 | 赛博朋克 / 冷峻 noir |
| 技术栈 | 纯 HTML5 + Canvas + JavaScript（零依赖） |
| 图片生成 | Pollinations.AI（完全免费，无需 API Key） |
| 部署 | GitHub Pages（静态托管） |
| 总大小 | ~900KB |

---

## 免费文生图工作流

### Pollinations.AI

完全免费，无需注册，无需 API Key，国内可用。

**API 调用方式：**
```
https://image.pollinations.ai/prompt/{URL编码的提示词}?width=宽&height=高&seed=种子&model=flux&nologo=true
```

**参数说明：**

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `prompt` | 提示词（URL 编码） | 描述越详细越好 |
| `width` | 图片宽度 | 960（背景）、512（肖像） |
| `height` | 图片高度 | 640（背景）、512（肖像） |
| `seed` | 随机种子 | 固定值可复现，推荐 `2087` |
| `model` | 模型 | `flux`（推荐，质量最好） |
| `nologo` | 去水印 | `true` |

**Python 调用模板：**
```python
import urllib.request
import urllib.parse

def generate_image(prompt, filename, width=1024, height=1024, seed=2087):
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&model=flux&nologo=true"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
        with open(filename, "wb") as f:
            f.write(data)
    print(f"✅ {filename} ({len(data)//1024}KB)")
```

**提示词技巧：**
- 开头加风格描述：`pixel art style, 16-bit retro game aesthetic`
- 加氛围词：`dark moody atmosphere, rain-soaked, neon accents`
- 明确用途：`game background art, no characters`
- 保持一致：多个图使用相同的风格前缀

---

## 游戏引擎架构

### 文件结构
```
last-signal/
├── index.html          # 游戏主文件（HTML + CSS + JS 全内联）
├── gen_assets.py       # 素材生成脚本（Pollinations.AI）
└── assets/
    ├── bg_apartment.png    # 场景背景 (960×640)
    ├── bg_street.png
    ├── bg_bar.png
    ├── bg_alley.png
    ├── bg_tower_exterior.png
    ├── bg_server_room.png
    ├── bg_rooftop.png
    ├── bg_office.png
    ├── portrait_kai.png    # 角色肖像 (512×512)
    └── portrait_oracle.png
```

### 核心模块

#### 1. Game 对象（全局状态管理）
```javascript
const Game = {
  canvas, ctx,           // Canvas 渲染
  currentScene,          // 当前场景 ID
  inventory: [],         // 背包物品列表
  flags: {},             // 剧情标记（布尔值）
  images: {},            // 预加载的图片缓存
  selectedItem,          // 当前选中的物品
  dialogueActive,        // 对话是否激活
};
```

#### 2. 场景系统 (SCENES)
每个场景包含：
```javascript
{
  name: "场景显示名称",
  background: "bg_xxx",      // 对应 assets/ 下的图片名
  onEnter() {},              // 进入场景时的自动对话
  hotspots: [                // 可点击区域
    {
      x, y, w, h,           // 点击区域坐标 (960×640 坐标系)
      label: "▸ 提示文字",
      condition() {},        // 可选：显示条件
      action() {},           // 点击后的逻辑
    }
  ]
}
```

#### 3. 对话系统
```javascript
// 无选项对话
await Game.showDialogue("说话者", "对话文本");

// 有选项对话
const choice = await Game.showDialogue("说话者", "文本", [
  { text: "选项1" },
  { text: "选项2" },
]);
// choice === 0 表示选了第一个选项
```

**特性：**
- 打字机效果（25ms/字）
- 点击继续
- 分支选项

#### 4. 物品系统
```javascript
// 物品定义
const ITEMS = {
  datachip: { name: "数据芯片", icon: "💾", desc: "描述" },
};

// 操作
Game.addItem("datachip");        // 获得物品
Game.removeItem("datachip");     // 移除物品
Game.hasItem("datachip");        // 检查是否拥有
Game.selectedItem                // 当前选中的物品（用于"使用"交互）
```

#### 5. 剧情标记系统
```javascript
Game.flags.visited_bar = true;   // 设置标记
if (Game.flags.visited_bar) {}   // 检查标记
```
用于控制：
- 对话是否重复播放
- 热点区域是否显示
- 剧情分支走向

#### 6. 音效系统
```javascript
Game.sfx("click");     // 点击
Game.sfx("pickup");    // 拾取
Game.sfx("door");      // 开门
Game.sfx("error");     // 错误
Game.sfx("success");   // 成功
```
使用 Web Audio API，纯代码合成，无需音频文件。

#### 7. 渲染流程
```
loadImages() → goScene(sceneId) → render()
  → 绘制背景图
  → 绘制暗角效果 (radial gradient)
  → HUD (物品栏 + 场景名)
```

---

## 素材生成流程

### 一键生成全部素材
```bash
cd last-signal
python3 gen_assets.py
```

### 交互区域 Mask 系统

游戏使用**二值 mask 图片**做像素级碰撞检测，替代传统的矩形热区。

**原理：**
- 每个场景有一张 `assets/masks/{sceneId}_mask.png`（960×640 灰度图）
- 白色区域 (RGB > 128) = 可交互
- 黑色区域 = 背景（不可交互）
- 鼠标移动时读取 mask 对应像素颜色，判断是否命中

**生成流程：**
1. 用视觉模型（mimo-omni）分析场景图片，识别可交互物体
2. 在 `gen_masks.py` 中定义每个场景的交互区域（支持 rect / ellipse / polygon）
3. 运行 `python3 gen_masks.py` 生成 mask PNG

**Mask 数据格式（`gen_masks.py` 中）：**
```python
"scene_name": [
    {
        "name": "terminal",
        "shape": "rect",        # rect / ellipse / polygon
        "cx_pct": 45,           # 中心 X (百分比)
        "cy_pct": 45,           # 中心 Y (百分比)
        "w_pct": 22,            # 宽度 (百分比)
        "h_pct": 25,            # 高度 (百分比)
    },
    {
        "name": "chair",
        "shape": "polygon",
        "polygon_points_pct": [  # 多边形顶点 (百分比)
            [73, 60], [70, 85], [79, 86], [82, 60]
        ],
    },
]
```

**视觉反馈：**
- 默认状态：mask 边缘呼吸闪烁（绿色像素点）
- 悬停状态：mask 边缘发光轮廓 + 半透明绿色覆盖 + 浮动标签
- 无 mask 时 fallback 到矩形高亮

### 添加新场景的步骤

1. **在 `gen_assets.py` 中添加 prompt**
```python
PROMPTS["bg_newscene"] = f"A new cyberpunk scene, {STYLE}, 具体描述..."
```

2. **在 `index.html` 的 `SCENES` 中添加场景**
```javascript
newscene: {
  name: "新场景名称",
  background: "bg_newscene",
  onEnter() { /* 入场对话 */ },
  hotspots: [ /* 可点击区域 */ ],
}
```

3. **如果有新物品，在 `ITEMS` 中添加**
```javascript
newitem: { name: "物品名", icon: "🔑", desc: "描述" },
```

4. **运行生成脚本并推送**
```bash
python3 gen_assets.py
git add -A && git commit -m "add new scene" && git push
```

---

## 部署到 GitHub Pages

### 首次部署
```bash
# 1. 初始化项目
cd project-name
git init && git checkout -b main

# 2. 推送到 GitHub（需要 token 或 SSH）
git remote add origin https://github.com/用户名/仓库名.git
git add . && git commit -m "init"
git push -u origin main

# 3. 启用 Pages
# GitHub → 仓库 → Settings → Pages → Source → Deploy from branch → main → / (root)
# 或通过 API：
curl -X PUT -H "Authorization: token TOKEN" \
  https://api.github.com/repos/用户/仓库/pages \
  -d '{"source":{"branch":"main","path":"/"}}'
```

### 访问地址
```
https://用户名.github.io/仓库名/
```

### 更新游戏
```bash
git add -A && git commit -m "update" && git push
# Pages 自动重新构建，几分钟后生效
```

---

## 复用指南

### 如何用这套工作流制作新游戏

1. **确定剧本和场景**
   - 写一个简单的剧情大纲
   - 列出所有场景（5-10个为佳）
   - 列出关键物品和角色

2. **生成素材**
   - 修改 `gen_assets.py` 中的 PROMPTS
   - 保持统一的 STYLE 前缀以保证视觉一致性
   - 运行脚本批量生成

3. **编写场景逻辑**
   - 复制 `index.html` 的引擎代码
   - 在 `SCENES` 对象中定义每个场景
   - 用 `flags` 控制剧情分支

4. **测试与部署**
   - 本地用 `python3 -m http.server 8765` 测试
   - 推送到 GitHub Pages

### 推荐 Prompt 模板

**背景场景（960×640）：**
```
A [场景描述], pixel art style, 16-bit retro game aesthetic, [风格], [色调], [特殊元素], game background art, adventure game scene
```

**角色肖像（512×512）：**
```
Character portrait, pixel art, 16-bit retro style, [角色描述], [风格], dark background, upper body portrait, limited color palette, no text
```

**道具图标（256×256）：**
```
Pixel art game item icon, [物品描述], 16-bit retro style, transparent background, clean pixels, game asset
```

---

*文档生成日期：2026-04-22*
*项目仓库：https://github.com/ampresent/last-signal*
*在线游玩：https://ampresent.github.io/last-signal/*
