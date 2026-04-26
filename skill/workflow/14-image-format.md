# 图片格式规范

**所有生成的图片素材必须为 WebP 格式。** 不再允许生成 PNG、JPG、BMP 等其他格式。

## 规则

- 生成脚本输出必须为 `.webp`（`ffmpeg -i input -quality 90 output.webp`）
- 如需从 PNG 转换：`ffmpeg -y -i input.png -quality 90 output.webp`
- `.gitignore` 已屏蔽 `.png`、`.jpg`、`.jpeg`、`.bmp`、`.gif` 等格式
- 例外：`preview_*.gif`（行走预览 GIF）允许保留

## 历史存量

`assets/masks/` 下 67 个同名 png+webp 文件已用 png 内容覆盖 webp（2026-04-26）。
