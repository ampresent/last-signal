# Animation Frame Remake Plan

## Goal
Remake all 96 animation frames (8 scenes × 12 frames) following the docs specs.

## Approach

### Phase 1: Apartment (Depth Lighting)
- Script: `gen_depth_lighting.py`
- Method: HuggingFace Serverless Inference API (Depth-Anything-V2-Large) → deterministic per-pixel lighting
- 3 light sources with 120° phase offset sine curves
- Output: `assets/bg_apartment_f0~f11.png`

### Phase 2: All 8 Scenes (Depth Lighting, unified)
- Script: `gen_depth_lighting.py`
- Method: Depth-Anything-V2-Large → deterministic per-pixel lighting per scene
- All 8 scenes with unique light source configurations
- Each: 12 frames with perfect loop closure (integer-multiple phase frequencies)

### Commit Strategy
- Commit after each phase
- Push to origin/main

---
*Created: 2026-04-22*
*Updated: 2026-04-23 — Switched to HuggingFace Serverless Inference API*
