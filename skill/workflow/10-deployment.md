# 部署到 GitHub Pages

## 初始部署

```bash
git remote add origin https://github.com/用户/仓库名.git
git add . && git commit -m "init" && git push -u origin main
# GitHub → Settings → Pages → Deploy from branch → main → / (root)
```

## 更新

```bash
git add -A && git commit -m "update" && git push
```

## GitHub Actions Workflow

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
  workflow_dispatch:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      - uses: actions/deploy-pages@v4
```

## 本地测试

```bash
python3 -m http.server 8765
# 打开 http://localhost:8765
```

## 构建优化

```bash
python3 build.py              # PNG→WebP 转换 + 更新引用
python3 build.py --dry-run    # 仅统计
python3 build.py --restore    # 恢复 .png 引用
```

---
**Related reference:** [deployment](../reference/deployment.md)
