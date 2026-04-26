---
name: last-signal-workflow
description: LAST SIGNAL game development workflow — AI-powered point-and-click adventure game creation with Pollinations.AI, Depth-Anything, MobileSAM, and real-time WebGL lighting. Use when working on the LAST SIGNAL project or adapting its engine for new games.
---

# LAST SIGNAL Workflow

Complete development workflow for the LAST SIGNAL cyberpunk point-and-click adventure game.

## Quick Reference

| Task | Command |
|------|---------|
| Generate base assets | `python3 gen_assets.py` |
| Generate depth + lighting | `python3 gen_depth_lighting.py` |
| Generate masks | `python3 gen_masks.py` |
| Generate character sprites | `python3 gen_character_views.py` |
| Build (PNG→WebP) | `python3 build.py` |
| Local test | `python3 -m http.server 8765` |

## Chapter Index

See `skill/workflow/` for detailed documentation split by topic:
- `01-project-overview.md` — Project structure and tech stack
- `02-ai-image-generation.md` — Pollinations.AI text2img
- `03-depth-lighting.md` — Depth-Anything + programmatic lighting
- `04-vfx-engine.md` — Canvas particle system
- `05-lighting-engine.md` — WebGL real-time lighting
- `06-dialogue-system.md` — Dialogue API and expressions
- `07-character-system.md` — Sprite workflow and movement
- `08-mask-system.md` — MobileSAM + Omni mask pipeline
- `09-asset-pipeline.md` — Generation scripts and build
- `10-deployment.md` — GitHub Pages deployment

## Engine Reference

See `skill/reference/` for reusable component documentation:
- `engine-core.md` — Game object, scene system, rendering loop
- `asset-pipeline.md` — AI asset generation pipeline
- `lighting-system.md` — WebGL depth lighting engine
- `vfx-system.md` — Particle effects engine
- `gameplay.md` — Dialogue, inventory, spawn system
- `deployment.md` — Build and deploy
- `pitfalls.md` — Known issues and solutions

## Environment Setup

```bash
# HuggingFace mirror (required in China)
export HF_ENDPOINT=https://hf-mirror.com

# Dependencies
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow

# MobileSAM models
bash setup.sh
```

## Key Configuration Files

| File | Purpose |
|------|---------|
| `lighting-config.json` | Per-scene light source definitions |
| `gen_assets.py` SCENE_PROMPTS | Scene image generation prompts |
| `gen_depth_lighting.py` SCENE_LIGHTS | Lighting frame parameters |
| `gen_masks.py` SCENES | Object bboxes + walkable/water zones |
| `index.html` SCENES | Game scene definitions + hotspots |
| `index.html` VFX.SCENE_CONFIG | Per-scene particle effects |
