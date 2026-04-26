# 游戏引擎架构

## 文件结构

```
last-signal/
├── index.html              # 游戏主文件（HTML + CSS + JS 全内联）
├── lighting-engine.js      # WebGL 光照引擎
├── lighting-config.json    # 各场景光源配置
├── lighting-editor.html    # 可视化光照编辑器
├── gen_assets.py           # 素材生成（Pollinations.AI）
├── gen_depth_lighting.py   # Depth Lighting 渲染器
├── gen_masks.py            # MobileSAM + Omni mask 生成器
├── gen_character_views.py   # 角色视角生成
├── cutout_from_sheet.py    # 从 sprite sheet 逐帧抠图
├── greenscreen_cutout.py   # 绿幕 GrabCut 抠图（推荐）
├── build.py                # PNG→WebP 构建脚本
├── WORKFLOW.md             # 工作流文档
├── SETUP.md                # 环境搭建指南
├── DEVLOG.md               # 开发日志
└── assets/
    ├── bg_*_f0~f11.png     # 每场景 12 帧动画
    ├── *_depth.png          # 各场景深度图缓存
    ├── portrait_*.png       # 角色肖像
    ├── expressions/         # 角色表情变体（3角色×6表情）
    ├── sprites/
    │   ├── cutout_{char}_{dir}.png    # 角色抠图（源文件）
    │   ├── raw_{char}_{dir}.png       # 原始角色图
    │   └── {char}_{dir}_f{0-7}.webp   # 逐帧 WebP（游戏加载）
    └── masks/
        ├── {scene}_mask.png           # 组合 mask
        ├── {scene}_{obj}_mask.png     # 单独物体 mask
        ├── {scene}_walkable_mask.png  # 可行走区域 mask
        ├── {scene}_water_mask.png     # 水面区域 mask
        └── mask_metadata.json
```

## 核心模块

### Game 对象

```javascript
const Game = {
  canvas, ctx,           // Canvas 渲染
  currentScene,          // 当前场景 ID
  bgFrames: {},          // sceneName → [Image, ...] 动画帧
  currentFrame,          // 当前帧索引
  frameInterval: 800,    // 帧间隔 ms
  inventory: [],         // 背包
  flags: {},             // 剧情标记
  masks, objMasks,       // Mask 数据
  _edgeCache,            // 预计算边缘像素
  _labelCache,           // 预计算标签位置
  _overlayCache,         // 预计算遮罩 canvas
};
```

### 场景系统

```javascript
{
  name: "场景名称",
  background: "bg_xxx",
  onEnter() {},          // 入场对话
  hotspots: [{
    x, y, w, h,          // 坐标（降级用）
    label: "▸ 提示",
    maskId: "obj_id",    // 对应 mask
    condition() {},       // 显示条件
    action() {},          // 点击逻辑
  }]
}
```

### 渲染循环

```
loadImages() → loadMasks() → 预计算边缘/标签/遮罩
goScene(sceneId) → VFX.init(sceneId) → startRenderLoop()
  每帧 (~60fps):
    drawImage(bgFrames[currentFrame])
    VFX.render(ctx, dt, sceneId)
    drawHotspotOverlays()  // 预计算，零扫描
```

### 性能优化

- **willReadFrequently: true** — CPU canvas 加速 getImageData
- **预计算 mask 数据** — 加载时算好，渲染时只画点
- **render 零扫描** — 不扫像素，只遍历预计算数组

### 物品/音效系统

```javascript
Game.addItem("datachip");  Game.hasItem("datachip");
Game.sfx("click"|"pickup"|"door"|"error"|"success");
```

---
**Related reference:** [engine-core](../reference/engine-core.md)
