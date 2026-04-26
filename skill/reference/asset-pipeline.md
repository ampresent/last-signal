# Asset Pipeline

> AI-powered asset generation: text-to-image, depth estimation, mask creation, sprite workflow.

## Overview

```
gen_assets.py           → Scene backgrounds + character portraits (Pollinations.AI)
gen_depth_lighting.py   → Depth maps + animated lighting frames (Depth-Anything + programmatic)
gen_masks.py            → Interaction/walkable/water masks (MobileSAM + Omni)
gen_character_views.py  → Character sprites from video (ffmpeg + GrabCut)
build.py                → PNG→WebP conversion + HTML reference update
```

## 1. Scene Image Generation (gen_assets.py)

Uses **Pollinations.AI** — completely free, no API key, works in China.

### Text-to-Image (GET)
```
https://image.pollinations.ai/prompt/{prompt}?width=960&height=640&seed=2087&model=flux&nologo=true
```

### Image-to-Image (POST)
```bash
curl -X POST \
  "https://image.pollinations.ai/prompt/{prompt}?width=960&height=640&seed=2087&model=flux&nologo=true" \
  -F "image=@base_image.png" \
  -o output.png
```

### Parameters
| Param | Description | Recommended |
|-------|-------------|-------------|
| `prompt` | Text prompt (URL-encoded) | Detailed, specific |
| `width/height` | Dimensions | 960×640 (backgrounds) / 512×512 (portraits) |
| `seed` | RNG seed | `2087` (fixed for reproducibility) |
| `model` | Model | `flux` |
| `nologo` | Remove watermark | `true` |

### Prompt Template Pattern
```python
STYLE = "pixel art style, 16-bit retro game aesthetic, cyberpunk noir, ..."

SCENE_PROMPTS = {
    "bg_apartment": "A small dark cyberpunk apartment room, {style}, ...",
    "bg_street": "A rainy cyberpunk street at night, {style}, ...",
    # Add your scenes here
}
```

### Output
- `assets/bg_{scene}.png` — Base scene images
- `assets/portrait_{char}.png` — Character portraits

## 2. Depth + Lighting (gen_depth_lighting.py)

### Pipeline
```
bg_{scene}.png
    │
    ▼
Depth-Anything-V2-Large (hf-mirror.com) → {scene}_depth.png
    │
    ▼
Per-frame lighting (programmatic 2D):
  - N light sources with position, color, radius, phase
  - Per-pixel: distance falloff + depth modulation + shadow ray march
  - Additive blending: base + lighting
    │
    ▼
assets/bg_{scene}_f0~f11.png (12 frames, seamless loop)
```

### Usage
```bash
export HF_ENDPOINT=https://hf-mirror.com

python3 gen_depth_lighting.py                    # All scenes
python3 gen_depth_lighting.py --scene apartment   # Single scene
python3 gen_depth_lighting.py --lighting-only     # Reuse cached depth maps
python3 gen_depth_lighting.py --depth-only        # Depth maps only
```

### Scene Light Configuration
```python
SCENE_LIGHTS = {
    "apartment": [
        {
            "id": "moonlight",
            "type": "directional",
            "color": [0.15, 0.2, 0.4],
            "intensity": 0.8,
            "dir": [0.3, -0.7],
            "phase": {"type": "sine", "speed": 1.0},
        },
        {
            "id": "screen_glow",
            "type": "point",
            "x": 0.81, "y": 0.62,
            "color": [0.2, 1.0, 0.4],
            "radius": 95,
            "intensity": 4.0,
            "depth": 0.28,
            "phase": {"type": "burst", "speed": 2.85},
        },
    ]
}
```

### Phase Function Types
| Type | Description | Use Case |
|------|-------------|----------|
| `steady` | Constant intensity | Background ambient |
| `sine` | Sinusoidal breathing | Moonlight, gentle glow |
| `pulse` | Configurable min/max/speed | Neon signs |
| `flicker` | Irregular on/off | Broken lights |
| `car_sweep` | Moving directional sweep | Car headlights |
| `lightning` | Mostly dark, brief flash | Storm effects |
| `burst` | Rapid irregular bursts | CRT screens |

### Dependencies
- `torch`, `transformers`, `timm` — Depth-Anything inference
- `opencv-python-headless`, `numpy` — Image processing

## 3. Mask Generation (gen_masks.py)

### Three-Step Pipeline
```
bg_{scene}.png
    │
    ▼
Step 1: Omni → object detection → bboxes
    │
    ▼
Step 2: MobileSAM (ONNX) → precise binary masks
    │
    ▼
Step 3: Omni → layer verification (PASS/FAIL)
    │
    ▼
assets/masks/{scene}_{obj}_mask.png
assets/masks/{scene}_mask.png (combined)
assets/masks/{scene}_walkable_mask.png
assets/masks/{scene}_water_mask.png
```

### Scene Config in gen_masks.py
```python
SCENES = {
    "apartment": {
        "image": "bg_apartment.png",
        "spawn": [0.48, 0.78],
        "objects": [
            {"id": "terminal", "label": "终端", "bbox": [500, 380, 900, 627]},
            {"id": "window", "label": "窗户", "bbox": [10, 140, 460, 590]},
        ],
        "walkable": {"bbox": [60, 400, 900, 627], "label": "房间地面"},
        "water": None,
        "edge_transitions": [
            {"id": "to_street", "label": "出门", "zone": "bottom",
             "size": 50, "target": "street"},
        ]
    }
}
```

### Usage
```bash
python3 gen_masks.py                    # All scenes
python3 gen_masks.py --scene apartment   # Single scene
python3 gen_masks.py --skip-omni-detect  # Use predefined bboxes
python3 gen_masks.py --skip-verify       # Skip layer verification
python3 gen_masks.py --no-push           # Don't auto-push
```

### Mask Format
- White (>128) = active area
- Black = background
- All masks stored as WebP lossless

## 4. Character Sprites (gen_character_views.py)

### Pipeline: Video → Sprite Sheet
```
1. Generate character front view (Pollinations text2img)
2. img2img → 4 direction views (front/back/left/right)
3. Generate walking video per direction (AI video platform)
4. ffmpeg → extract frames at original FPS
5. Multi-modal model → direction identification + frame selection
6. HSV green screen + GrabCut → character cutout
7. Horizontal mirror → fill missing directions
8. Crop + compose → sprite sheet + preview GIF
```

### Green Screen Cutout (greenscreen_cutout.py)
```python
def green_screen_cutout(img_rgb):
    """HSV green detection + GrabCut fine segmentation."""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    green_mask = cv2.inRange(hsv, [35,50,50], [85,255,255])
    # Use as GrabCut seed → precise foreground extraction
```

**Critical**: Process at 128px width, then downscale to 64px. Never erode edges.

### Output
- `assets/sprites/{char}_{dir}_f{0-7}.webp` — Walking frames (8 per direction)
- `assets/sprites/sprite_sheet_{char}.png` — Full sprite sheet
- `assets/sprites/preview_{char}.gif` — Preview for manual QA

## 5. Build (build.py)

```bash
python3 build.py              # Full build: convert + update references
python3 build.py --dry-run    # Stats only, no modification
python3 build.py --restore    # Revert to .png references
```

### Compression Presets
| Asset | Quality | Mode | Reduction |
|-------|---------|------|-----------|
| Background frames | q80 | lossy | ~90% |
| Depth maps | q85 | lossy | ~80% |
| Portraits | q85 | lossy | ~75% |
| Sprites | q90 | alpha | ~70% |
| Masks | q100 | lossless | ~60% |

## Adding a New Scene

1. Add prompt to `gen_assets.py` SCENE_PROMPTS
2. Add light config to `gen_depth_lighting.py` SCENE_LIGHTS
3. Add scene config to `gen_masks.py` SCENES (objects, walkable, water)
4. Add scene definition to `index.html` SCENES
5. Add VFX config to `VFX.SCENE_CONFIG`
6. Add lighting config to `lighting-config.json`
7. Run generation scripts
8. `git add -A && git commit && git push`

---
**Related workflow chapters:** [02-ai-image-generation](../workflow/02-ai-image-generation.md) · [03-depth-lighting](../workflow/03-depth-lighting.md) · [07-character-system](../workflow/07-character-system.md) · [07b-sprite-sheet](../workflow/07b-sprite-sheet.md) · [08-mask-system](../workflow/08-mask-system.md) · [09-asset-pipeline](../workflow/09-asset-pipeline.md)
