# Scripts

These are the core generation and build scripts used by the LAST SIGNAL workflow.

All scripts are designed to be run from the **project root** directory (not from inside `skill/scripts/`).

## Scripts

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

These scripts are bundled here so the skill directory is self-contained.
The canonical copies live in the project root for actual execution.
