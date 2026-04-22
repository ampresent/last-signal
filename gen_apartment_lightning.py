#!/usr/bin/env python3
"""
LAST SIGNAL - Depth-Based Lighting for Apartment Scene
Uses Depth-Anything-V2-Large for depth estimation, then renders
deterministic per-pixel lighting with shadow ray marching.

Usage:
    python3 gen_apartment_lighting.py                    # full pipeline
    python3 gen_apartment_lighting.py --depth-only       # only generate depth map
    python3 gen_apartment_lighting.py --lighting-only    # only render frames (reuse depth)
"""

import argparse
import math
import os
import sys
import time

import cv2
import numpy as np

# ============================================================
# Config
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DEPTH_OUT = os.path.join(ASSETS_DIR, "apartment_depth.png")
BASE_IMG = os.path.join(ASSETS_DIR, "bg_apartment.png")
FRAME_FMT = os.path.join(ASSETS_DIR, "bg_apartment_f{}.png")

NUM_FRAMES = 12

# Light sources: sinusoidal intensity, 120° phase offsets
LIGHT_SOURCES = [
    {
        "name": "terminal",
        "x": 680, "y": 480,
        "color": (0.2, 0.9, 0.3),      # cyberpunk green
        "radius": 350,
        "intensity_lo": 0.6, "intensity_hi": 1.0,
        "phase_deg": 0,
    },
    {
        "name": "ceiling",
        "x": 480, "y": 80,
        "color": (1.0, 0.85, 0.6),      # warm amber
        "radius": 500,
        "intensity_lo": 0.5, "intensity_hi": 0.9,
        "phase_deg": 120,
    },
    {
        "name": "window",
        "x": 50, "y": 350,
        "color": (0.3, 0.5, 0.8),       # cool blue
        "radius": 600,
        "intensity_lo": 0.3, "intensity_hi": 0.7,
        "phase_deg": 240,
    },
]

AMBIENT = 0.05
SHADOW_STEPS = 48
SHADOW_DEPTH_THRESH = 0.03


# ============================================================
# Depth Estimation
# ============================================================

def load_depth_model():
    """Load Depth-Anything-V2-Large via transformers."""
    import torch
    from transformers import AutoModelForDepthEstimation, AutoImageProcessor

    model_id = "depth-anything/Depth-Anything-V2-Large-hf"
    print(f"  📦 Loading {model_id}...")
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForDepthEstimation.from_pretrained(model_id)
    model.eval()
    return model, processor


def estimate_depth(img_bgr, model, processor):
    """Run depth estimation. Returns float32 [H,W] in [0,1], 0=near 1=far."""
    import torch
    from PIL import Image

    h, w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)

    inputs = processor(images=pil_img, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)

    depth = outputs.predicted_depth.squeeze().numpy()
    depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_CUBIC)

    # Normalize: higher value = farther
    d_min, d_max = depth.min(), depth.max()
    if d_max > d_min:
        depth = (depth - d_min) / (d_max - d_min)
    else:
        depth = np.zeros_like(depth)

    # Invert: DA2 outputs inverse depth (closer = higher), so flip to 0=near
    depth = 1.0 - depth

    # Bilateral filter: smooth gradients, keep edges
    depth_u8 = (depth * 255).astype(np.uint8)
    depth_filtered = cv2.bilateralFilter(depth_u8, 9, 75, 75)
    return depth_filtered.astype(np.float32) / 255.0


# ============================================================
# Lighting Renderer
# ============================================================

def get_intensity(light, frame_idx):
    """Sinusoidal intensity for a light at given frame."""
    lo, hi = light["intensity_lo"], light["intensity_hi"]
    phase = math.radians(light["phase_deg"])
    t = (frame_idx / NUM_FRAMES) * 2 * math.pi
    val = math.sin(t + phase)
    return lo + (hi - lo) * (val + 1) / 2


def render_frame(base_img, depth_map, lights):
    """Render one frame with per-pixel lighting + shadow ray march."""
    h, w = base_img.shape[:2]
    base_f = base_img.astype(np.float32) / 255.0
    light_map = np.full((h, w, 3), AMBIENT, dtype=np.float32)

    py_grid, px_grid = np.mgrid[0:h, 0:w].astype(np.float32)

    for light in lights:
        # Distance attenuation
        dist = np.sqrt((px_grid - light["x"])**2 + (py_grid - light["y"])**2)
        r = light["radius"]
        atten = 1.0 / (1.0 + (dist * dist) / (r * r))

        # Depth modulation
        depth_factor = 1.0 - depth_map * 0.7

        # Shadow ray march (every 2px for speed)
        shadow = np.ones((h, w), dtype=np.float32)
        step = 2
        for sy in range(0, h, step):
            for sx in range(0, w, step):
                shadow[sy, sx] = _ray_march(sx, sy, light, depth_map)
        # Nearest-neighbor fill for skipped pixels
        if step > 1:
            for sy in range(0, h, step):
                for sx in range(1, w, step):
                    shadow[sy, sx] = shadow[sy, sx - 1]
            for sy in range(1, h, step):
                shadow[sy, :] = shadow[sy - 1, :]

        intensity = light["current_intensity"]
        cr, cg, cb = light["color"]
        factor = intensity * atten * depth_factor * shadow
        light_map[:, :, 0] += cr * factor
        light_map[:, :, 1] += cg * factor
        light_map[:, :, 2] += cb * factor

    result = np.clip(base_f * light_map, 0, 1.0)
    return (result * 255).astype(np.uint8)


def _ray_march(px, py, light, depth_map):
    """March shadow ray from pixel to light. Returns [0.15, 1.0]."""
    lx, ly = light["x"], light["y"]
    dx, dy = lx - px, ly - py
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1:
        return 1.0

    sx = dx / dist
    sy = dy / dist
    seg = dist / SHADOW_STEPS
    cur_depth = depth_map[py, px]
    h, w = depth_map.shape

    for i in range(1, SHADOW_STEPS):
        mx = int(px + sx * seg * i)
        my = int(py + sy * seg * i)
        if mx < 0 or mx >= w or my < 0 or my >= h:
            break
        if depth_map[my, mx] > cur_depth + SHADOW_DEPTH_THRESH:
            return 0.15  # shadowed (ambient leak)
    return 1.0


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth-only", action="store_true")
    parser.add_argument("--lighting-only", action="store_true")
    args = parser.parse_args()

    print("=" * 50)
    print("🔦 LAST SIGNAL - Depth Lighting (DA2-Large)")
    print("=" * 50)

    base = cv2.imread(BASE_IMG)
    if base is None:
        sys.exit(f"❌ Cannot read {BASE_IMG}")
    print(f"  📷 Base: {base.shape[1]}×{base.shape[0]}")

    # --- Depth ---
    if not args.lighting_only:
        t0 = time.time()
        model, processor = load_depth_model()
        print(f"  ⏱️  Model loaded: {time.time()-t0:.1f}s")

        t0 = time.time()
        depth = estimate_depth(base, model, processor)
        print(f"  ⏱️  Depth estimated: {time.time()-t0:.1f}s")

        cv2.imwrite(DEPTH_OUT, (depth * 255).astype(np.uint8))
        print(f"  💾 Saved: {DEPTH_OUT}")

        del model, processor
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if args.depth_only:
            print("\n✅ Depth-only done.")
            return
    else:
        if not os.path.exists(DEPTH_OUT):
            sys.exit(f"❌ No depth map: {DEPTH_OUT}")
        depth = cv2.imread(DEPTH_OUT, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
        print(f"  🗺️  Depth map loaded")

    # --- Render ---
    print(f"\n  🎬 Rendering {NUM_FRAMES} frames...")
    os.makedirs(ASSETS_DIR, exist_ok=True)
    frames = []

    for fi in range(NUM_FRAMES):
        t0 = time.time()
        lights = []
        for src in LIGHT_SOURCES:
            l = dict(src)
            l["current_intensity"] = get_intensity(src, fi)
            lights.append(l)

        frame = render_frame(base, depth, lights)
        frames.append(frame)
        cv2.imwrite(FRAME_FMT.format(fi), frame)

        sz = os.path.getsize(FRAME_FMT.format(fi)) // 1024
        dt = time.time() - t0
        intens = "  ".join(f"{l['name'][0]}:{l['current_intensity']:.2f}" for l in lights)
        print(f"    ✅ f{fi:2d}  {sz:5d}KB  {dt:4.1f}s  [{intens}]")

    # --- Quality ---
    print(f"\n📊 Frame diffs (vs f0):")
    for i in range(1, len(frames)):
        d = np.mean(cv2.absdiff(frames[0], frames[i]))
        bar = "█" * int(d) + "░" * max(0, 20 - int(d))
        tag = "微妙" if d < 5 else "可见" if d < 15 else "明显"
        print(f"    f0↔f{i:2d}: {d:5.1f}  {bar}  [{tag}]")

    loop = np.mean(cv2.absdiff(frames[0], frames[-1]))
    print(f"    循环 f0↔f{NUM_FRAMES-1}: {loop:.1f}")
    print(f"\n✅ Done.")


if __name__ == "__main__":
    main()
