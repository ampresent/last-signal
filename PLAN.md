# Animation Frame Remake Plan

## Goal
Remake all 96 animation frames (8 scenes × 12 frames) following the docs specs.

## Approach

### Phase 1: Apartment (Depth Lighting)
- Script: `gen_apartment_lighting.py`
- Method: Depth-Anything-V2-Large → deterministic per-pixel lighting
- 3 light sources with 120° phase offset sine curves
- Output: `assets/bg_apartment_f0~f11.png`

### Phase 2: Other 7 Scenes (img2img + Optical Flow)
- Script: `gen_ai_frames.py`
- Method: Pollinations.AI img2img keyframes → OpenCV Farneback optical flow interpolation
- Scenes: street, bar, alley, tower_exterior, server_room, rooftop, office
- Each: 4 keyframes × 3 interpolated = 12 frames + loop closure

### Commit Strategy
- Commit after each phase
- Push to origin/main

---
*Created: 2026-04-22*
