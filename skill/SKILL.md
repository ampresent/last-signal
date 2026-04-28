---
name: last-signal-workflow
description: LAST SIGNAL game development workflow — AI-powered point-and-click adventure game creation with Pollinations.AI, Depth-Anything, MobileSAM, and real-time WebGL lighting. Use when working on the LAST SIGNAL project or adapting its engine for new games.
---

# LAST SIGNAL Workflow

Complete development workflow for the LAST SIGNAL cyberpunk point-and-click adventure game.

## Quick Reference

| Task | Command |
|------|---------|
| Generate base assets | `python3 scripts/gen_assets.py` |
| Generate depth + lighting | `python3 scripts/gen_depth_lighting.py` |
| Generate masks | `python3 scripts/gen_masks.py` |
| **Iterative ground detection** | `python3 scripts/gen_ground_mask.py [--scene apartment\|alley] [--max-rounds 3]` |
| Generate character sprites | `python3 scripts/gen_character_views.py` |
| Sprite sheet cutout (RMBG-1.4) | `python3 scripts/rmbg14_cutout.py <direction> <frames_dir>` |
| Fix sprite size across directions | `python3 scripts/fix_sprite_scale.py` |
| Build (PNG→WebP) | `python3 scripts/build.py` |
| Local test | `python3 -m http.server 8765` |

> **Sprite sheet 生成**：视频→帧→方向识别→关键帧→抠图→sprite sheet，完整流程见 `skill/workflow/07b-sprite-sheet.md`。
>
> **⚠️ 抠图方案**：逐帧推理（方案A）比拼 sheet（方案B）更快。
> 实测 8 帧：A=8.4s vs B=12.0s（CPU 环境）。见 `SETUP.md` §10。

## From-Scratch Reproduction

服务器重启后所有本地文件丢失？只剩 GitHub 远程仓库是持久的。
完整重建流程见 **[`SETUP.md` §从零复现指南](./SETUP.md#从零复现指南服务器重建--新机器部署)**。

关键步骤摘要：

```bash
# 1. Clone + checkout
git clone https://TOKEN@github.com/ampresent/last-signal.git && cd last-signal
git checkout feat/rmbg2-cutout

# 2. pip 依赖（阿里云源 + R2 torch + 清华 transformers/timm/kornia）
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow boto3
# → R2 下载 torch wheel → pip install
pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
  --ignore-installed rich transformers timm kornia

# 3. RMBG-1.4 模型（R2 下载 ~169MB）
# → models/RMBG-1.4/ (7 files)

# 4. 视频 → 帧 → 关键帧裁剪 → rmbg14_cutout.py 抠图
```

> **并发提示**：步骤 2（pip）、步骤 3（模型下载）、步骤 4（视频下载+帧提取）可并行执行。

## Chapter Index

See `skill/workflow/` for detailed documentation split by topic:

**Core Systems:**
- `01-project-overview.md` — Project structure and tech stack
- `02-ai-image-generation.md` — Pollinations.AI text2img
- `03-depth-lighting.md` — Depth-Anything + programmatic lighting
- `04-vfx-engine.md` — Canvas particle system
- `05-lighting-engine.md` — WebGL real-time lighting
- `05b-lighting-editor.md` — Visual lighting parameter editor

**Gameplay:**
- `06-dialogue-system.md` — Dialogue API and expressions
- `07-character-system.md` — Character sprite workflow and movement
- `07b-sprite-sheet.md` — Full video-to-sprite-sheet pipeline (8 steps)
- `08-mask-system.md` — MobileSAM + Omni mask pipeline
- `15-spawn-system.md` — Character spawn point system

**Infrastructure:**
- `09-asset-pipeline.md` — Generation scripts and build
- `10-deployment.md` — GitHub Pages deployment
- `11-engine-architecture.md` — File structure, core modules, performance patterns
- `12-pitfalls.md` — Battle-tested solutions for common issues
- `13-reuse-guide.md` — How to build a new game with this engine
- `14-image-format.md` — WebP-only format rules

## Engine Reference

See `skill/reference/` for reusable component documentation:
- `engine-core.md` — Game object, scene system, rendering loop
- `asset-pipeline.md` — AI asset generation pipeline
- `lighting-system.md` — WebGL depth lighting engine
- `vfx-system.md` — Particle effects engine
- `gameplay.md` — Dialogue, inventory, spawn system
- `deployment.md` — Build and deploy
- `pitfalls.md` — Known issues and solutions

## Bundled Scripts

Essential scripts are bundled in `skill/scripts/` so the skill directory is self-contained:

| Script | Purpose |
|--------|---------|
| `scripts/gen_assets.py` | Scene image + portrait generation (Pollinations.AI) |
| `scripts/gen_depth_lighting.py` | Depth maps + programmatic lighting |
| `scripts/gen_masks.py` | MobileSAM + Omni mask pipeline |
| `scripts/gen_ground_mask.py` | **Iterative ground detection** — Omni identifies small patches → SAM segments → Omni reviews → repeat. For walkable mask generation. |
| `scripts/gen_character_views.py` | Character perspective generation |
| `scripts/cutout_from_sheet.py` | Sprite sheet frame cutout |
| `scripts/rmbg14_cutout.py` | RMBG-1.4 background removal (any background). Requires: torch, transformers, timm, kornia |
| `scripts/fix_sprite_scale.py` | Normalize sprite content height across directions |
| `scripts/build.py` | PNG→WebP build |
| `scripts/setup.sh` | Environment setup |

> **Note:** Scripts must be run from the project root. See `skill/scripts/README.md`.

## Environment Setup

See **[`SETUP.md`](./SETUP.md)** for full setup instructions (R2 resources, torch install, known issues).

Quick start:

```bash
cd /root/.openclaw/workspace/last-signal
export HF_ENDPOINT=https://hf-mirror.com
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow
bash skill/scripts/setup.sh
```

> **⚠️ RMBG-1.4 额外依赖**：`setup.sh` 不装 torch/transformers/timm/kornia。
> 这些是 RMBG-1.4 抠图脚本的必须依赖，需手动安装（见 SETUP.md §3b）。

## Key Configuration Files

| File | Purpose |
|------|---------|
| `lighting-config.json` | Per-scene light source definitions |
| `scripts/gen_assets.py` SCENE_PROMPTS | Scene image generation prompts |
| `scripts/gen_depth_lighting.py` SCENE_LIGHTS | Lighting frame parameters |
| `scripts/gen_masks.py` SCENES | Object bboxes + walkable/water zones |
| `index.html` SCENES | Game scene definitions + hotspots |
| `index.html` VFX.SCENE_CONFIG | Per-scene particle effects |
