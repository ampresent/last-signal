# 项目概览

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

## 文件结构

```
last-signal/
├── index.html              # 游戏主文件（HTML + CSS + JS 全内联）
├── lighting-engine.js      # WebGL 光照引擎
├── lighting-config.json    # 各场景光源配置
├── lighting-editor.html    # 可视化光照编辑器
├── gen_assets.py           # 素材生成（Pollinations.AI 文生图 + 角色肖像）
├── gen_depth_lighting.py   # Depth Lighting 渲染器
├── gen_masks.py            # MobileSAM + Omni mask 生成器
├── gen_character_views.py   # 角色视角生成
├── greenscreen_cutout.py   # 绿幕 GrabCut 抠图
├── build.py                # PNG→WebP 构建脚本
├── WORKFLOW.md             # 完整工作流文档
├── SETUP.md                # 环境搭建指南
├── DEVLOG.md               # 开发日志
└── assets/
    ├── bg_*_f0~f11.png     # 每场景 12 帧动画
    ├── *_depth.png          # 各场景深度图
    ├── portrait_*.png       # 角色肖像
    ├── expressions/         # 角色表情变体
    ├── sprites/             # 角色行走帧
    └── masks/               # 交互/可行走/水面 masks
```
