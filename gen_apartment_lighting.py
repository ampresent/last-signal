#!/usr/bin/env python3
"""
gen_apartment_lighting.py — Pre-rendered depth lighting for apartment scene

Uses Depth-Anything-V2-Large (via HuggingFace mirror + local inference) for
depth estimation + programmatic 2D depth-based lighting with 3 simultaneous
light sources (120° phase offset sinusoidal curves).

Model download: uses HF_ENDPOINT (default: hf-mirror.com) for domestic access.
Inference: local via transformers pipeline (CPU).

Usage:
    python3 gen_apartment_lighting.py              # full pipeline
    python3 gen_apartment_lighting.py --depth-only  # depth map only
    python3 gen_apartment_lighting.py --lighting-only # lighting only (reuse cached depth)
"""

import sys
import os
import time
import argparse
import math
from pathlib import Path

import numpy as np
import cv2
import torch

# ── Constants ──────────────────────────────────────────────────────
BASE_IMAGE = "assets/bg_apartment.png"
DEPTH_CACHE = "assets/apartment_depth.png"
OUTPUT_FMT = "assets/bg_apartment_f{frame}.png"
NUM_FRAMES = 12
SHADOW_STEPS = 64  # design spec: 64 steps
AMBIENT = 0.05

# ── HuggingFace Mirror ────────────────────────────────────────────
HF_MODEL = "depth-anything/Depth-Anything-V2-Large-hf"
# Use hf-mirror.com for domestic (China) access, override with HF_ENDPOINT env
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

# Set HF endpoint before importing transformers
os.environ["HF_ENDPOINT"] = HF_ENDPOINT


def load_depth_model():
    """Load Depth-Anything-V2-Large via transformers pipeline."""
    from transformers import pipeline

    print(f"  Loading model from {HF_ENDPOINT}...")
    print(f"  (First run downloads ~1.3GB, cached for subsequent runs)")

    t0 = time.time()
    pipe = pipeline(
        "depth-estimation",
        model=HF_MODEL,
        device="cpu",
        torch_dtype=torch.float32,
    )
    print(f"  ✓ Model loaded ({time.time()-t0:.1f}s)")
    return pipe


def generate_depth_map(pipe, base_image):
    """Generate depth map using transformers pipeline."""
    from PIL import Image

    pil_img = Image.fromarray(base_image)
    t0 = time.time()
    result = pipe(pil_img)
    print(f"  ✓ Inference done ({time.time()-t0:.1f}s)")

    depth = np.array(result["depth"])
    return depth.astype(np.float32)


def postprocess_depth(depth, target_h, target_w):
    """Normalize, resize, and smooth depth map."""
    # Resize to match base image if needed
    if depth.shape[:2] != (target_h, target_w):
        depth = cv2.resize(depth, (target_w, target_h),
                           interpolation=cv2.INTER_LINEAR)

    # Normalize to 0-255 (0=near, 255=far)
    depth_norm = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
    depth_u8 = (depth_norm * 255).astype(np.uint8)

    # Bilateral filter for smooth gradients while preserving edges
    depth_smooth = cv2.bilateralFilter(depth_u8, 9, 75, 75)

    return depth_smooth


# ── Light Source Definitions ───────────────────────────────────────
LIGHT_SOURCES = [
    # Terminal (green glow) — center of desk ~ (700, 500)
    {
        "name": "terminal",
        "pos": (700, 500),
        "color": np.array([0.2, 0.9, 0.3]),
        "intensity_range": (0.6, 1.0),
        "radius": 350.0,
        "phase_deg": 0,
    },
    # Ceiling light (warm amber) — center-top ~ (480, 80)
    {
        "name": "ceiling",
        "pos": (480, 80),
        "color": np.array([1.0, 0.85, 0.6]),
        "intensity_range": (0.5, 0.9),
        "radius": 500.0,
        "phase_deg": 120,
    },
    # Window ambient (cool blue) — left side ~ (50, 350)
    {
        "name": "window",
        "pos": (50, 350),
        "color": np.array([0.3, 0.5, 0.8]),
        "intensity_range": (0.3, 0.7),
        "radius": 600.0,
        "phase_deg": 240,
    },
]


def compute_lighting_for_frame(depth_map, frame_idx, img_h, img_w):
    """
    Compute per-pixel lighting for a single frame.

    Returns: lighting array (H, W, 3) in [0, 1] range.
    """
    depth_float = depth_map.astype(np.float32) / 255.0  # 0=near, 1=far

    # Pixel coordinate grids
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    # Total lighting accumulator
    total_light = np.zeros((img_h, img_w, 3), dtype=np.float32)
    total_light += AMBIENT  # base ambient

    for src in LIGHT_SOURCES:
        lx, ly = src["pos"]
        color = src["color"]
        r_min, r_max = src["intensity_range"]
        radius = src["radius"]
        phase_rad = math.radians(src["phase_deg"])

        # Sinusoidal intensity for this frame (seamless loop: f0 == f12)
        t = 2 * math.pi * frame_idx / NUM_FRAMES
        intensity = r_min + (r_max - r_min) * (0.5 + 0.5 * math.sin(t + phase_rad))

        # Distance from each pixel to light source
        dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2)

        # Inverse-square attenuation with radius clamp
        attenuation = 1.0 / (1.0 + (dist / radius) ** 2)

        # Depth modulation: closer surfaces get more light
        depth_factor = 1.0 - depth_float

        # Shadow ray march: step from pixel toward light, check depth occlusion
        shadow = ray_march_shadows(depth_float, (lx, ly), img_h, img_w)

        # Combine
        contrib = (color[np.newaxis, np.newaxis, :] *
                   intensity *
                   attenuation[:, :, np.newaxis] *
                   depth_factor[:, :, np.newaxis] *
                   shadow[:, :, np.newaxis])

        total_light += contrib

    return np.clip(total_light, 0.0, 1.5)


def ray_march_shadows(depth_map, light_pos, img_h, img_w):
    """March shadow rays from each pixel toward the light source."""
    lx, ly = light_pos
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    dx = lx - xx
    dy = ly - yy
    dist = np.sqrt(dx * dx + dy * dy)

    eps = 1e-8
    dx_norm = dx / (dist + eps)
    dy_norm = dy / (dist + eps)

    max_steps = SHADOW_STEPS
    step_dist = dist / max_steps

    shadow = np.ones((img_h, img_w), dtype=np.float32)
    current_depth = depth_map

    for step in range(1, max_steps + 1):
        sx = xx + dx_norm * step_dist * step
        sy = yy + dy_norm * step_dist * step

        sx_clamped = np.clip(sx, 0, img_w - 1).astype(np.int32)
        sy_clamped = np.clip(sy, 0, img_h - 1).astype(np.int32)

        sampled_depth = depth_map[sy_clamped, sx_clamped]
        shadow_mask = (sampled_depth > current_depth + 0.05).astype(np.float32)
        shadow *= (1.0 - shadow_mask)

    return shadow


def composite_frame(base_image, lighting):
    """Composite base image with lighting using additive blending (per design spec)."""
    base_float = base_image.astype(np.float32) / 255.0
    result = base_float + lighting
    result = np.clip(result * 255, 0, 255).astype(np.uint8)
    return result


def quality_report(frames):
    """Print quality metrics for generated frames."""
    print("\n── Quality Report ──")

    diffs = []
    for i in range(1, len(frames)):
        d = np.mean(cv2.absdiff(frames[i - 1], frames[i]))
        diffs.append(d)
        print(f"  f{i-1} → f{i}: mean diff = {d:.2f}")

    loop_diff = np.mean(cv2.absdiff(frames[0], frames[-1]))
    print(f"  f0 ↔ f11 (loop): mean diff = {loop_diff:.2f}")

    for i, f in enumerate(frames):
        peak = f.max()
        print(f"  f{i}: peak brightness = {peak}")

    avg_diff = np.mean(diffs)
    print(f"\n  Average inter-frame diff: {avg_diff:.2f}")
    if avg_diff > 20:
        print("  ⚠️  High inter-frame variation — check light params")
    elif avg_diff < 2:
        print("  ⚠️  Very low variation — lights may be too subtle")
    else:
        print("  ✓ Variation looks good")

    if loop_diff > 5:
        print(f"  ⚠️  Loop closure diff ({loop_diff:.2f}) > 5 — may see pop")
    else:
        print(f"  ✓ Loop closure smooth")


def main():
    parser = argparse.ArgumentParser(description="Apartment depth lighting renderer")
    parser.add_argument("--depth-only", action="store_true", help="Generate depth map only")
    parser.add_argument("--lighting-only", action="store_true", help="Lighting only (reuse cached depth)")
    args = parser.parse_args()

    start_all = time.time()

    # ── Load base image ──
    print("Loading base image...")
    base_image = cv2.imread(BASE_IMAGE)
    if base_image is None:
        print(f"  ✗ Cannot load {BASE_IMAGE}")
        sys.exit(1)
    base_rgb = cv2.cvtColor(base_image, cv2.COLOR_BGR2RGB)
    img_h, img_w = base_rgb.shape[:2]
    print(f"  ✓ {img_w}×{img_h}")

    # ── Generate or load depth map ──
    if args.lighting_only:
        print("Loading cached depth map...")
        depth_map = cv2.imread(DEPTH_CACHE, cv2.IMREAD_GRAYSCALE)
        if depth_map is None:
            print(f"  ✗ No cached depth at {DEPTH_CACHE}")
            sys.exit(1)
        print(f"  ✓ Loaded {DEPTH_CACHE}")
    else:
        print("Generating depth map (Depth-Anything-V2-Large via HF mirror)...")
        pipe = load_depth_model()
        raw_depth = generate_depth_map(pipe, base_rgb)
        depth_map = postprocess_depth(raw_depth, img_h, img_w)
        cv2.imwrite(DEPTH_CACHE, depth_map)
        print(f"  ✓ Depth map saved to {DEPTH_CACHE}")
        del pipe  # free memory

    if args.depth_only:
        print("\n✓ Depth-only mode complete.")
        return

    # ── Render frames ──
    print(f"\nRendering {NUM_FRAMES} frames...")
    frames = []

    for i in range(NUM_FRAMES):
        t0 = time.time()
        lighting = compute_lighting_for_frame(depth_map, i, img_h, img_w)
        frame = composite_frame(base_rgb, lighting)

        out_path = OUTPUT_FMT.format(frame=i)
        cv2.imwrite(out_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        frames.append(frame)

        dt = time.time() - t0
        print(f"  ✓ f{i} → {out_path} ({dt:.1f}s)")

    # ── Quality report ──
    quality_report(frames)

    total = time.time() - start_all
    print(f"\n✓ Done in {total:.1f}s")


if __name__ == "__main__":
    main()
