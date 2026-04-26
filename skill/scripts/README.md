# Scripts

Core generation and build scripts live in the **project root**, not here.

This directory is reserved for future skill-specific scripts that don't belong in the project root.

## Root Scripts

| Script | Purpose |
|--------|---------|
| `gen_assets.py` | Generate base scene images + character portraits (Pollinations.AI) |
| `gen_depth_lighting.py` | Depth-Anything depth maps + programmatic lighting |
| `gen_masks.py` | MobileSAM + Omni mask generation (objects, walkable, water) |
| `gen_character_views.py` | Character perspective generation |
| `cutout_from_sheet.py` | Frame-by-frame cutout from sprite sheets |
| `greenscreen_cutout.py` | HSV green-screen removal with Omni verification loop |
| `build.py` | PNG→WebP build + reference updates |
| `setup.sh` | Environment setup (MobileSAM models, dependencies) |

## Usage

```bash
# From project root:
export HF_ENDPOINT=https://hf-mirror.com
python3 gen_assets.py
python3 gen_depth_lighting.py
python3 gen_masks.py
# ...
```
