# Design: Pre-rendered Depth Lighting for Apartment Scene

**Date:** 2026-04-22
**Updated:** 2026-04-23 — Switched from local model to HuggingFace Serverless Inference API
**Scope:** Replace AI img2img animation with depth-based ray-traced lighting on `bg_apartment`
**Goal:** Eliminate frame instability while upgrading to simultaneous multi-source light interactions

---

## Problem

Current animation uses Pollinations img2img + OpenCV optical flow interpolation. Even with BLEND_ALPHA=0.55 and "same composition" prompts, frame-to-frame consistency is unreliable. Object morphing, color drift, and optical flow ghosting make the apartment scene feel jittery.

## Approach

Single base image + **Depth-Anything-V2-Large** depth estimation + programmatic 2D depth-based lighting. No AI generation per frame — fully deterministic, perfectly stable.

## Pipeline

```
bg_apartment.png (base)
       │
       ▼
  HuggingFace API (Depth-Anything-V2-Large) → depth_map.png (grayscale, 960×640)
       │
       ▼
  For each frame (f0–f11):
    ├─ Define light source parameters (position, color, intensity, radius)
    ├─ Per-pixel: compute lighting from all 3 sources
    │   ├─ distance attenuation (inverse square)
    │   ├─ depth modulation (closer surfaces brighter)
    │   └─ shadow ray march (depth occlusion test)
    ├─ Composite: base × (ambient + diffuse lighting)
    └─ Save frame PNG
       │
       ▼
  assets/bg_apartment_f0.png … bg_apartment_f11.png (overwrite)
```

## Components

### 1. Depth Map Generation (`gen_apartment_lighting.py`)

- Use **Depth-Anything-V2-Large** via HuggingFace Serverless Inference API
- API endpoint: `https://api-inference.huggingface.co/models/depth-anything/Depth-Anything-V2-Large-hf`
- Input: `bg_apartment.png` (960×640)
- Output: `assets/apartment_depth.png` (grayscale, 0=near, 255=far)
- Post-process: bilateral filter for smooth gradients while preserving object boundaries
- Cache: skip if depth map exists and is newer than base image
- Auth: optional `.hf-token` file or `HF_TOKEN` env var (for higher rate limits)

**Why Depth-Anything-V2 over MiDaS:**
- Higher accuracy, especially on fine structures and edges
- Better on stylized/pixel-art imagery (MiDaS struggles here)
- More robust depth ordering for lighting occlusion
- Same inference speed on CPU (~3-5s per image)

**Dependencies:** `requests`, `opencv-python-headless`, `numpy`
**API:** HuggingFace Serverless Inference (no local model deployment needed)

### 2. Rendering Masks

New masks for rendering only (separate from interaction masks):

| Mask | Purpose | Source |
|------|---------|--------|
| `light_terminal` | Terminal screen emissive region | Rect region + depth threshold |
| `light_ceiling` | Ceiling light fixture region | Rect region + depth threshold |
| `window_region` | Window opening (ambient light source) | Existing `apartment_window_mask` reused |
| `shadow_casters` | Desk, furniture edges that cast shadows | Depth gradient edges (auto-generated) |

Generated programmatically from depth map + hardcoded regions — no manual labeling needed beyond 3 rect coordinates for light sources.

### 3. Lighting Model

**Per-pixel computation for each light source:**

```
attenuation = 1.0 / (1.0 + d² / r²)    # inverse-square falloff with radius
depth_factor = 1.0 - depth[x,y]          # closer surfaces get more light
shadow = ray_march(pos, light_pos, depth_map)  # 1.0 = lit, 0.0 = shadowed
contribution = color × intensity × attenuation × depth_factor × shadow
```

**Ambient base:** very low (0.05) constant ambient so shadows aren't pure black

**Composite:** additive blending of all light contributions onto base image, clamped to [0, 255]

**Shadow ray march:** step from pixel toward light source along depth map. If any intermediate pixel has depth > current pixel depth + threshold → shadowed. Step count limited to 64 for performance.

### 4. Light Sources

Three simultaneous sources, each with a parameter curve across 12 frames:

#### Terminal (green glow)
- Position: center of desk surface (~700, 500)
- Color: `(0.2, 0.9, 0.3)` — cyberpunk green
- Intensity: sine wave, phase 0°, amplitude 0.6–1.0
- Radius: 350px

#### Ceiling light (warm point light)
- Position: center-top (~480, 80)
- Color: `(1.0, 0.85, 0.6)` — warm amber
- Intensity: sine wave, phase 120°, amplitude 0.5–0.9
- Radius: 500px

#### Window ambient (cool directional)
- Position: left side (~50, 350)
- Color: `(0.3, 0.5, 0.8)` — cool blue
- Intensity: sine wave, phase 240°, amplitude 0.3–0.7
- Radius: 600px (wide, soft)

**Phase offsets (120° apart):** When terminal is brightest, ceiling is mid-fade and window is dimmest. Creates the "simultaneous complex interaction" — lights continuously fight for dominance across the cycle.

```
Frame:  f0    f1    f2    f3    f4    f5    f6    f7    f8    f9    f10   f11
Term:   ■■■■  ■■■■  ■■■   ■■    ■     ▪     ▪     ■     ■■    ■■■   ■■■■  ■■■■
Ceil:   ▪     ■     ■■    ■■■   ■■■■  ■■■■  ■■■■  ■■■   ■■    ■     ▪     ▪
Window: ▪     ▪     ■     ■■    ■■■   ■■■■  ■■■■  ■■■■  ■■■   ■■    ■     ▪
```

Each cycle is seamless (sinusoidal, f0 == f12).

### 5. Output

- 12 PNG frames: `assets/bg_apartment_f0.png` through `assets/bg_apartment_f11.png`
- Direct overwrite of existing frames
- No changes to `index.html`, `WORKFLOW.md` VFX system, or mask files
- Depth map cached at `assets/apartment_depth.png`

### 6. New Script: `gen_apartment_lighting.py`

Single script, all logic inline. Flow:

```
1. Load base image
2. Generate/cache depth map (MiDaS)
3. Generate shadow caster edges from depth gradient
4. Define light source parameter curves (12 frames, sinusoidal)
5. For each frame:
   a. Compute per-pixel lighting from 3 sources
   b. Composite onto base image
   c. Save frame
6. Print quality report (frame diffs, peak brightness per source)
```

~150–200 lines of Python. Dependencies: `torch`, `torchvision`, `timm`, `cv2`, `numpy`.

## Trade-offs

| | This approach | Current img2img |
|---|---|---|
| Stability | Perfect — deterministic math | Unstable — AI randomness |
| Visual richness | Programmatic, clean | Organic but unpredictable |
| Speed | ~30s (CPU MiDaS + rendering) | ~3min (API calls + interpolation) |
| Flexibility | Adjust params, instant re-render | Re-prompt, hope for consistency |
| Artifact risk | None (no optical flow) | Ghosting, morphing, color drift |
| Depth accuracy | DA2-Large handles pixel art better than MiDaS | N/A |

**Risk:** Depth estimation on pixel art may still have edge artifacts. Mitigation: bilateral filter post-process + manual depth correction mask if needed. DA2-Large is significantly better than MiDaS on this style.

## Verification

After generation:
1. Visual check: open `f0–f11` in sequence, confirm smooth transitions
2. Diff check: `np.mean(cv2.absdiff(f0, fi))` should be 2–15 (subtle), not >20
3. Loop check: `f0 ↔ f11` diff should be minimal (<5)
4. Game check: `python3 -m http.server 8765`, open in browser, confirm apartment renders correctly
5. Commit + push

## Files Changed

| File | Action |
|------|--------|
| `gen_apartment_lighting.py` | **New** ✅ — depth lighting renderer (HF API) |
| `.hf-token` | Optional — HuggingFace API token for higher rate limits |
| `assets/apartment_depth.png` | Generated at runtime — cached depth map |
| `assets/bg_apartment_f0–f11.png` | Overwritten at runtime — 12 new frames |
| `WORKFLOW.md` | Update animation section with new pipeline description |

## Implementation Notes

### Model Loading Strategy

使用 HuggingFace Serverless Inference API：
- 端点：`https://api-inference.huggingface.co/models/depth-anything/Depth-Anything-V2-Large-hf`
- 认证：可选（`.hf-token` 文件或 `HF_TOKEN` 环境变量）
- 冷启动：首次调用可能需要 20-60s 加载模型，后续调用很快
- 自动重试：503（模型加载中）和 429（速率限制）自动重试

### Dependencies

```bash
pip install requests numpy opencv-python-headless
```

深度模型通过 HuggingFace Serverless Inference API 调用，无需本地安装 torch/transformers。

### Running

```bash
# Full pipeline (depth + lighting)
python3 gen_apartment_lighting.py

# Depth only
python3 gen_apartment_lighting.py --depth-only

# Lighting only (re-render with different params, reuse cached depth)
python3 gen_apartment_lighting.py --lighting-only
```

### Performance

- Depth estimation: ~5-15s (via HuggingFace API, depends on cold start)
- Frame rendering: ~15-25s per frame (64-step shadow ray march)
- Total: ~3-5 minutes for 12 frames

## Files NOT Changed

- `index.html` — no engine changes needed
- `gen_ai_frames.py` — kept as-is for other scenes
- `gen_anim_frames.py` — kept as-is (legacy fallback)
- `assets/masks/*` — interaction masks untouched
- `gen_masks.py` — untouched
