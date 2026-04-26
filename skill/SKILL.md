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
| Generate character sprites | `python3 scripts/gen_character_views.py` |
| Build (PNG→WebP) | `python3 scripts/build.py` |
| Local test | `python3 -m http.server 8765` |

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
| `scripts/gen_character_views.py` | Character perspective generation |
| `scripts/cutout_from_sheet.py` | Sprite sheet frame cutout |
| `scripts/greenscreen_cutout.py` | HSV green-screen removal + Omni verification |
| `scripts/build.py` | PNG→WebP build |
| `scripts/setup.sh` | Environment setup |

> **Note:** Scripts must be run from the project root. See `skill/scripts/README.md`.

## Environment Setup

```bash
# HuggingFace mirror (required in China)
export HF_ENDPOINT=https://hf-mirror.com

# Dependencies
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow

# MobileSAM models
bash scripts/setup.sh
```

## Key Configuration Files

| File | Purpose |
|------|---------|
| `lighting-config.json` | Per-scene light source definitions |
| `scripts/gen_assets.py` SCENE_PROMPTS | Scene image generation prompts |
| `scripts/gen_depth_lighting.py` SCENE_LIGHTS | Lighting frame parameters |
| `scripts/gen_masks.py` SCENES | Object bboxes + walkable/water zones |
| `index.html` SCENES | Game scene definitions + hotspots |
| `index.html` VFX.SCENE_CONFIG | Per-scene particle effects |
