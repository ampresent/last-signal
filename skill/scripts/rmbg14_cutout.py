#!/usr/bin/env python3
"""
RMBG-1.4 background removal for sprite frames.

Uses BRIA's RMBG-1.4 model (lighter, faster, no HF token needed).
Supports both single-frame and sheet (concatenated) modes.

Usage:
    python3 skill/scripts/rmbg14_cutout.py up /tmp/sprite-work/up_selected --char kai
    python3 skill/scripts/rmbg14_cutout.py up /tmp/sprite-work/up_selected --char kai --sheet
"""

import os
import sys
import subprocess
import argparse
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.transforms.functional import normalize as tv_normalize

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets/sprites"
MIMO_SCRIPT = "/root/.openclaw/skills/mimo-omni/mimo_api.sh"
CHAR = "kai"
TARGET_W = 64
TARGET_H = 128
# Scale character to 80% of canvas height to leave head/foot margin
HEIGHT_RATIO = 0.80

# RMBG-1.4 model — public, no token needed
MODEL_ID = "briaai/RMBG-1.4"


def load_model():
    """Load RMBG-1.4 model — local weights or HuggingFace download."""
    local_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "RMBG-1.4")
    local_path = os.path.abspath(local_path)

    if os.path.isfile(os.path.join(local_path, "model.safetensors")):
        print(f"  📦 Loading from local: {local_path}")
        t0 = time.time()
        model = _load_rmbg14(local_path)
        print(f"  ✓ Model loaded in {time.time() - t0:.1f}s")
        return model

    # Fallback: HuggingFace mirror (public, no token needed)
    print(f"  📦 Downloading {MODEL_ID} from HuggingFace mirror...")
    os.makedirs(local_path, exist_ok=True)
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=local_path,
        ignore_patterns=["*.md", "*.txt", ".gitattributes"],
    )
    t0 = time.time()
    model = _load_rmbg14(local_path)
    print(f"  ✓ Model loaded in {time.time() - t0:.1f}s")
    return model


def _load_rmbg14(model_dir):
    """Load RMBG-1.4 by manually loading weights (avoids transformers version issues)."""
    import importlib.util
    from safetensors.torch import load_file as load_safetensors

    # Add model dir to sys.path so MyConfig can be found
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    # Load MyConfig
    cfg_spec = importlib.util.spec_from_file_location("MyConfig", os.path.join(model_dir, "MyConfig.py"))
    cfg_mod = importlib.util.module_from_spec(cfg_spec)
    sys.modules["MyConfig"] = cfg_mod
    cfg_spec.loader.exec_module(cfg_mod)

    # Patch briarmbg relative import
    briar_src = os.path.join(model_dir, "briarmbg.py")
    with open(briar_src) as f:
        code = f.read()
    code = code.replace("from .MyConfig import RMBGConfig", "from MyConfig import RMBGConfig")

    patched = os.path.join(model_dir, "_briarmbg_patched.py")
    with open(patched, "w") as f:
        f.write(code)

    spec = importlib.util.spec_from_file_location("_briarmbg_patched", patched)
    briar_mod = importlib.util.module_from_spec(spec)
    sys.modules["briarmbg"] = briar_mod
    spec.loader.exec_module(briar_mod)

    # Instantiate model and load weights manually
    model = briar_mod.BriaRMBG()

    safetensors_path = os.path.join(model_dir, "model.safetensors")
    if os.path.isfile(safetensors_path):
        state_dict = load_safetensors(safetensors_path)
    else:
        pth_path = os.path.join(model_dir, "pytorch_model.bin")
        state_dict = torch.load(pth_path, map_location="cpu")

    model.load_state_dict(state_dict, strict=False)
    model.eval()
    return model


def remove_background(model, pil_image):
    """
    Run RMBG-1.4 on a PIL image, return RGBA image with transparent background.

    RMBG-1.4 preprocessing:
      - resize to 1024x1024
      - divide by 255
      - normalize(mean=[0.5,0.5,0.5], std=[1.0,1.0,1.0])

    RMBG-1.4 postprocessing:
      - min-max normalize the raw output → 0-255 mask
    """
    import torch.nn.functional as F
    from torchvision.transforms.functional import normalize as tv_normalize

    orig_w, orig_h = pil_image.size

    # Preprocess: RMBG-1.4 style
    im = np.array(pil_image.convert("RGB"))
    im_tensor = torch.tensor(im, dtype=torch.float32).permute(2, 0, 1)
    im_tensor = F.interpolate(im_tensor.unsqueeze(0), size=[1024, 1024], mode="bilinear")
    image = torch.divide(im_tensor, 255.0)
    image = tv_normalize(image, [0.5, 0.5, 0.5], [1.0, 1.0, 1.0])

    with torch.no_grad():
        result = model(image)

    # Postprocess: RMBG-1.4 style (min-max normalize)
    raw = result[0][0]
    raw = torch.squeeze(F.interpolate(raw, size=[orig_h, orig_w], mode="bilinear"), 0)
    ma = torch.max(raw)
    mi = torch.min(raw)
    mask_norm = (raw - mi) / (ma - mi)
    mask_arr = (mask_norm * 255).permute(1, 2, 0).cpu().data.numpy().astype(np.uint8)
    mask_arr = np.squeeze(mask_arr)

    # Threshold at 128 (midpoint of 0-255 range)
    alpha = (mask_arr > 128).astype(np.uint8) * 255

    # Build RGBA
    arr = np.array(pil_image.convert("RGBA"))
    arr[:, :, 3] = alpha
    arr[alpha == 0, :3] = 0

    return Image.fromarray(arr)


def remove_background_sheet(model, sheet_image, cols=4, rows=2):
    """
    Remove background from a sheet image (multiple frames tiled).
    Returns list of individual RGBA frames.
    """
    sw, sh = sheet_image.size
    fw = sw // cols
    fh = sh // rows

    # Process entire sheet at once
    rgba_sheet = remove_background(model, sheet_image)

    # Split back into frames
    frames = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * fw, r * fh
            frame = rgba_sheet.crop((x0, y0, x0 + fw, y0 + fh))
            frames.append(frame)
    return frames


def verify_cutout(webp_path):
    """Check for background residue AND character completeness."""
    try:
        result = subprocess.run(
            ["bash", MIMO_SCRIPT, "image", webp_path,
             "检查这个角色sprite：1.背景是否完全透明（有无残留背景）？"
             "2.角色身体/四肢是否完整（有没有被切掉的部分）？"
             "3.边缘是否干净（有无锯齿或毛边）？简短回答每个问题。"],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        has_residue = "残留" in output or "不透明" in output
        has_incomplete = "不完整" in output or "切掉" in output or "缺失" in output or "被切" in output
        passed = not has_residue and not has_incomplete
        return passed, output
    except Exception as e:
        return False, str(e)


def finalize_frame(rgba):
    """Crop to content, scale with margin, and center on target canvas."""
    bbox = rgba.getbbox()
    if bbox is None:
        return None

    content = rgba.crop(bbox)
    # Scale to fit HEIGHT_RATIO of canvas height (leave margin for head/feet)
    max_h = int(TARGET_H * HEIGHT_RATIO)
    scale = max_h / content.height
    if scale > 1.0:
        scale = 1.0  # Don't upscale
    new_w = int(content.width * scale)
    new_h = int(content.height * scale)
    content = content.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    offset_x = (TARGET_W - new_w) // 2
    # Center vertically with slight upward bias (character feet anchor)
    offset_y = (TARGET_H - new_h) // 2
    canvas.paste(content, (offset_x, offset_y))
    return canvas


def main():
    parser = argparse.ArgumentParser(description="RMBG-1.4 sprite cutout")
    parser.add_argument("direction", nargs="?", default="left")
    parser.add_argument("input_dir", nargs="?", default=None)
    parser.add_argument("--char", default=CHAR)
    parser.add_argument("--sheet", action="store_true",
                        help="Process as 4x2 sheet (faster, less memory)")
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip omni verification")
    args = parser.parse_args()

    direction = args.direction
    input_dir = args.input_dir or f"/root/.openclaw/workspace/{direction}_selected"
    char = args.char

    if not os.path.isdir(input_dir):
        print(f"❌ Input directory not found: {input_dir}")
        sys.exit(1)

    files = sorted([f for f in os.listdir(input_dir) if f.endswith('.png')])
    print(f"RMBG-1.4 cutout — {char} / {direction}: {len(files)} frames")
    if args.sheet:
        print(f"  Sheet mode: {args.cols}x{args.rows}")
    print()

    # Load model once
    model = load_model()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.sheet:
        # --- Sheet mode: tile frames, process once, split ---
        print(f"  🧩 Building {args.cols}x{args.rows} sheet...")
        t_sheet = time.time()

        # Load and resize all frames to same size
        pil_frames = []
        for fname in files:
            img = Image.open(os.path.join(input_dir, fname)).convert("RGB")
            pil_frames.append(img)

        # Assume all frames same size
        fw, fh = pil_frames[0].size
        sheet = Image.new("RGB", (fw * args.cols, fh * args.rows))
        for i, img in enumerate(pil_frames):
            r, c = divmod(i, args.cols)
            sheet.paste(img, (c * fw, r * fh))

        print(f"  Sheet: {sheet.size[0]}x{sheet.size[1]} ({time.time()-t_sheet:.1f}s)")

        # Process sheet
        t0 = time.time()
        result_frames = remove_background_sheet(model, sheet, args.cols, args.rows)
        elapsed = time.time() - t0
        print(f"  ✓ Sheet processed in {elapsed:.1f}s ({elapsed/len(files):.1f}s/frame)")

        results = []
        for idx, rgba in enumerate(result_frames):
            output_path = os.path.join(OUTPUT_DIR, f"{char}_{direction}_f{idx}.webp")
            canvas = finalize_frame(rgba)
            if canvas is None:
                print(f"  ⚠️  Frame {idx}: empty — skipping")
                results.append((files[idx], False, 0))
                continue

            canvas.save(output_path, "WebP", lossless=True, quality=100)
            alpha = np.array(canvas)[:, :, 3]
            fg_pct = (alpha > 0).sum() / alpha.size * 100
            print(f"  {char}_{direction}_f{idx}.webp — fg={fg_pct:.1f}%")

            if not args.no_verify:
                passed, reason = verify_cutout(output_path)
                print(f"    {'✅ CLEAN' if passed else f'❌ {reason[:60]}'}")

            results.append((files[idx], True, fg_pct))

    else:
        # --- Single-frame mode ---
        results = []
        total_time = 0
        for idx, fname in enumerate(files):
            input_path = os.path.join(input_dir, fname)
            output_path = os.path.join(OUTPUT_DIR, f"{char}_{direction}_f{idx}.webp")
            print(f"--- {char}_{direction}_f{idx}.webp ---")

            t0 = time.time()
            img = Image.open(input_path).convert("RGB")
            rgba = remove_background(model, img)
            canvas = finalize_frame(rgba)
            elapsed = time.time() - t0
            total_time += elapsed

            if canvas is None:
                print(f"  ⚠️  Empty result — skipping")
                results.append((fname, False, 0))
                continue

            canvas.save(output_path, "WebP", lossless=True, quality=100)
            alpha = np.array(canvas)[:, :, 3]
            fg_pct = (alpha > 0).sum() / alpha.size * 100
            print(f"  fg={fg_pct:.1f}% ({elapsed:.1f}s)", end="")

            if not args.no_verify:
                passed, reason = verify_cutout(output_path)
                print(f" {'✅ CLEAN' if passed else f'❌ {reason[:60]}'}")
            else:
                print(f" ✓")

            results.append((fname, True, fg_pct))

        print(f"\n  Total inference: {total_time:.1f}s ({total_time/len(files):.1f}s/frame)")

    # Summary
    print(f"\n{'='*50}")
    ok_count = sum(1 for _, ok, _ in results if ok)
    print(f"Results: {ok_count}/{len(results)} processed")
    for fname, ok, fg_pct in results:
        status = "✅" if ok else "⚠️"
        print(f"  {status} {fname} (fg={fg_pct:.1f}%)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
