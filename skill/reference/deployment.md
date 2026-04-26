# Deployment

> GitHub Pages deployment, build optimization, and asset management.

## GitHub Pages

### Initial Setup
```bash
git remote add origin https://github.com/user/repo.git
git add . && git commit -m "init" && git push -u origin main
# GitHub → Settings → Pages → Deploy from branch → main → / (root)
```

### GitHub Actions Workflow

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      - uses: actions/deploy-pages@v4
```

## Build Script (build.py)

Converts PNG assets to WebP and updates HTML references.

```bash
python3 build.py              # Full build
python3 build.py --dry-run    # Stats only
python3 build.py --restore    # Revert to .png
```

### Compression Strategy

| Asset | Quality | Mode | Typical Reduction |
|-------|---------|------|-------------------|
| Backgrounds | q80 | lossy | ~90% |
| Depth maps | q85 | lossy | ~80% |
| Portraits | q85 | lossy | ~75% |
| Expressions | q85 | lossy | ~75% |
| Sprites | q90 | lossy+alpha | ~70% |
| Masks | q100 | lossless | ~60% |

### Process
1. Scan for PNG files matching patterns
2. Convert to WebP with appropriate quality/mode
3. Update all references in `index.html`
4. Optionally delete original PNGs

## Image Format Rules

**All generated assets must be WebP.** PNG/JPG/BMP/GIF are not allowed (except `preview_*.gif`).

- Generation scripts output WebP directly
- `.gitignore` blocks `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`
- Exception: `preview_*.gif` (walking preview GIFs)

## Local Development

```bash
python3 -m http.server 8765
# Open http://localhost:8765
```

No build step needed for development — the engine reads PNG/WebP directly.

## File Size Budget

Target: **< 1MB** total for the game (excluding assets served separately).

| Component | Size |
|-----------|------|
| `index.html` | ~180KB (HTML + CSS + JS all inline) |
| `lighting-engine.js` | ~15KB |
| `lighting-config.json` | ~17KB |
| Total code | ~212KB |

Assets are loaded on demand per scene.

## Git Workflow

```bash
# After changes
git add -A && git commit -m "description" && git push

# .gitignore excludes:
# - .png, .jpg, .jpeg, .bmp, .gif (except preview_*.gif)
# - .github-token, .hf-token, .s3cfg
# - models/, __pycache__/
```

---
**Related workflow chapters:** [10-deployment](../workflow/10-deployment.md) · [14-image-format](../workflow/14-image-format.md)
