# 🎮 LAST SIGNAL

> 最后的信号 — 一款赛博朋克 point & click 冒击游戏

**在线游玩：https://ampresent.github.io/last-signal/**

## 剧情

2087年，第三次网络崩溃之后。政府瘫痪，企业接管一切。

你是**凯**，前刑侦局探员。三年前你的搭档死在 ECHO 公司的实验室里，官方说是"事故"。直到有一天，幽灵黑客 **Oracle** 发来一条加密信号：

> *"我知道真相。来找我。"*

在霓虹街的酒吧、阴暗的后巷、ECHO 公司的塔楼中穿行，揭开 LASTLIGHT 项目的秘密。

## 特性

- 🎨 **全部素材由 AI 生成** — 使用 Pollinations.AI（完全免费）
- 🕹️ **经典 point & click 玩法** — 探索、对话、收集物品、解谜
- 🔀 **双结局** — 你的选择决定故事走向
- 🌐 **纯前端** — HTML5 + Canvas + JS，零依赖，可部署到任何静态托管
- 📦 **< 1MB** — 轻量到极致

## 文件结构

```
├── index.html          # 游戏主文件
├── gen_assets.py       # AI 素材生成脚本
├── WORKFLOW.md         # 完整工作流文档（复用指南）
└── assets/             # 游戏图片素材
```

## 本地运行

```bash
cd last-signal
python3 -m http.server 8765
# 打开 http://localhost:8765
```

## 重新生成素材

```bash
pip install pillow  # 仅 gen_assets.py 需要
python3 gen_assets.py
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 渲染 | HTML5 Canvas |
| 逻辑 | 原生 JavaScript |
| 图片生成 | Pollinations.AI (Flux 模型) |
| 音效 | Web Audio API（代码合成） |
| 托管 | GitHub Pages |

## 复用

想用这套工作流制作自己的 point & click 游戏？查看 [WORKFLOW.md](WORKFLOW.md)。

## License

MIT
