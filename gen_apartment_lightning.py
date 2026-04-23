#!/usr/bin/env python3
"""
gen_apartment_lighting.py — Pre-rendered depth lighting for apartment scene

Uses Depth-Anything-V2-Large for depth estimation + programmatic 2D depth-based
lighting with 3 simultaneous light sources (120° phase offset sinusoidal curves).

Model loading 3-level fallback:
  1. Official repo: depth_anything_v2_repo/ + local .pth checkpoint
  2. transformers: HuggingFace DepthAnythingV2ForDepthEstimation
  3. timm: ViT-Large backbone + custom DPT head

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
import subprocess
from pathlib import Path

import numpy as np
import cv2
import torch

# ── Constants ──────────────────────────────────────────────────────
BASE_IMAGE = "assets/bg_apartment.png"
DEPTH_CACHE = "assets/apartment_depth.png"
OUTPUT_FMT = "assets/bg_apartment_f{frame}.png"
INPUT_SIZE = 518  # DA2 input size (must be multiple of 14)
NUM_FRAMES = 12
SHADOW_STEPS = 64  # design spec: 64 steps
AMBIENT = 0.05
CPU_LIMIT = 0.95  # max CPU usage fraction
FRAME_SLEEP = 0.05  # seconds to sleep between frames for CPU breathing

# ── Light Source Definitions ───────────────────────────────────────
# Each: (x, y, color_rgb, intensity_base, intensity_amp, radius)
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


def download_model_from_r2():
    """Download depth model checkpoint from R2 if not present."""
    ckpt_path = "models/depth_anything_v2_vitl.pth"
    if os.path.exists(ckpt_path):
        return ckpt_path

    print("  ↓ Downloading model from R2...")
    os.makedirs("models", exist_ok=True)
    try:
        subprocess.run(
            ["s3cmd", "--region=auto", "get",
             "s3://mystore/depth_anything_v2_vitl.pth", ckpt_path],
            check=True, capture_output=True, text=True
        )
        print(f"  ✓ Model downloaded to {ckpt_path}")
        return ckpt_path
    except subprocess.CalledProcessError as e:
        print(f"  ✗ R2 download failed: {e.stderr}")
        return None


def load_depth_model_official():
    """Fallback 1: Official repo + local checkpoint."""
    repo_dir = Path(__file__).parent / "depth_anything_v2_repo"
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repo not found: {repo_dir}")

    sys.path.insert(0, str(repo_dir))
    from depth_anything_v2.dpt import DepthAnythingV2

    ckpt_path = download_model_from_r2()
    if not ckpt_path:
        raise FileNotFoundError("No checkpoint available")

    model = DepthAnythingV2(encoder='vitl', features=256,
                            out_channels=[256, 512, 1024, 1024])
    state = torch.load(ckpt_path, map_location='cpu', weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model, "official"


def load_depth_model_transformers():
    """Fallback 2: HuggingFace transformers pipeline."""
    from transformers import pipeline

    pipe = pipeline(
        "depth-estimation",
        model="depth-anything/Depth-Anything-V2-Large-hf",
        device="cpu",
        torch_dtype=torch.float32,
    )
    return pipe, "transformers"


def load_depth_model_timm():
    """Fallback 3: timm ViT-Large backbone."""
    import timm

    # Simple approach: use timm's depth estimation if available
    # This is a simplified fallback — may not produce as good results
    model = timm.create_model("vit_large_patch14_224", pretrained=False, num_classes=0)

    ckpt_path = download_model_from_r2()
    if ckpt_path:
        state = torch.load(ckpt_path, map_location='cpu', weights_only=True)
        # Try loading with strict=False (keys may not match exactly)
        model.load_state_dict(state, strict=False)

    model.eval()
    return model, "timm"


def load_depth_model():
    """Load depth model with 3-level fallback."""
    errors = []

    # Try official repo first
    try:
        model, method = load_depth_model_official()
        print(f"  ✓ Model loaded via {method}")
        return model, method
    except Exception as e:
        errors.append(f"official: {e}")

    # Try transformers
    try:
        model, method = load_depth_model_transformers()
        print(f"  ✓ Model loaded via {method}")
        return model, method
    except Exception as e:
        errors.append(f"transformers: {e}")

    # Try timm
    try:
        model, method = load_depth_model_timm()
        print(f"  ✓ Model loaded via {method}")
        return model, method
    except Exception as e:
        errors.append(f"timm: {e}")

    print("  ✗ All model loading methods failed:")
    for err in errors:
        print(f"    - {err}")
    sys.exit(1)


def generate_depth_map_official(model, base_image):
    """Generate depth map using official repo's infer_image."""
    bgr = cv2.cvtColor(base_image, cv2.COLOR_RGB2BGR)
    depth = model.infer_image(bgr, input_size=INPUT_SIZE)
    return depth


def generate_depth_map_transformers(pipe, base_image):
    """Generate depth map using transformers pipeline."""
    from PIL import Image

    pil_img = Image.fromarray(base_image)
    result = pipe(pil_img)
    depth = np.array(result["depth"])
    return depth.astype(np.float32)


def generate_depth_map(model, base_image, method="official"):
    """Generate depth map from base image using DA2-Large."""
    if method == "official":
        depth = generate_depth_map_official(model, base_image)
    elif method == "transformers":
        depth = generate_depth_map_transformers(model, base_image)
    else:
        raise ValueError(f"Unknown method: {method}")

    # Normalize to 0-255 (0=near, 255=far)
    depth_norm = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
    depth_u8 = (depth_norm * 255).astype(np.uint8)

    # Bilateral filter for smooth gradients while preserving edges
    depth_smooth = cv2.bilateralFilter(depth_u8, 9, 75, 75)

    return depth_smooth


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

    return np.clip(total_light, 0.0, 1.5)  # allow slight overexposure for HDR feel


def ray_march_shadows(depth_map, light_pos, img_h, img_w):
    """
    March shadow rays from each pixel toward the light source.

    For each pixel, step along the line toward the light. If any intermediate
    pixel has depth significantly greater than the current pixel → shadowed.

    Returns: shadow map (H, W) in [0, 1] where 1.0 = fully lit.
    """
    lx, ly = light_pos
    yy, xx = np.mgrid[0:img_h, 0:img_w].astype(np.float32)

    # Direction vectors from each pixel to light
    dx = lx - xx
    dy = ly - yy
    dist = np.sqrt(dx * dx + dy * dy)

    # Normalize direction
    eps = 1e-8
    dx_norm = dx / (dist + eps)
    dy_norm = dy / (dist + eps)

    # Step size: total distance / num_steps
    max_steps = SHADOW_STEPS
    step_dist = dist / max_steps

    shadow = np.ones((img_h, img_w), dtype=np.float32)
    current_depth = depth_map

    for step in range(1, max_steps + 1):
        # Sample position along the ray
        sx = xx + dx_norm * step_dist * step
        sy = yy + dy_norm * step_dist * step

        # Clamp to image bounds
        sx_clamped = np.clip(sx, 0, img_w - 1).astype(np.int32)
        sy_clamped = np.clip(sy, 0, img_h - 1).astype(np.int32)

        # Look up depth at sampled position
        sampled_depth = depth_map[sy_clamped, sx_clamped]

        # If sampled depth is significantly greater than current pixel depth → occluded
        shadow_mask = (sampled_depth > current_depth + 0.05).astype(np.float32)

        # Accumulate shadow (once shadowed, stays shadowed)
        shadow *= (1.0 - shadow_mask)

    return shadow


def composite_frame(base_image, lighting):
    """Composite base image with lighting using additive blending (per design spec)."""
    base_float = base_image.astype(np.float32) / 255.0

    # Additive blending: base + lighting, clamped to [0, 1]
    result = base_float + lighting

    # Clamp and convert back
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

    # Loop closure
    loop_diff = np.mean(cv2.absdiff(frames[0], frames[-1]))
    print(f"  f0 ↔ f11 (loop): mean diff = {loop_diff:.2f}")

    # Peak brightness per frame
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
        print("Generating depth map (DA2-Large)...")
        t0 = time.time()
        model, method = load_depth_model()
        depth_map = generate_depth_map(model, base_rgb, method)
        cv2.imwrite(DEPTH_CACHE, depth_map)
        print(f"  ✓ Depth map saved to {DEPTH_CACHE} ({time.time()-t0:.1f}s)")
        del model  # free memory

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

        # CPU breathing: sleep between frames to stay under 95% CPU
        time.sleep(FRAME_SLEEP)

    # ── Quality report ──
    quality_report(frames)

    total = time.time() - start_all
    print(f"\n✓ Done in {total:.1f}s")


if __name__ == "__main__":
    main()
