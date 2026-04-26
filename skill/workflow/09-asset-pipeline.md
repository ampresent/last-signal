# 素材生成流程

## 一键生成

```bash
export HF_ENDPOINT=https://hf-mirror.com
python3 gen_assets.py              # 基础图
python3 gen_depth_lighting.py      # 所有场景 Depth Lighting
```

## 分步生成（推荐顺序）

```bash
export HF_ENDPOINT=https://hf-mirror.com

python3 gen_assets.py              # 1. 基础场景图 + 角色肖像
python3 gen_depth_lighting.py      # 2. Depth Lighting
python3 gen_masks.py               # 3. MobileSAM + Omni mask
python3 gen_character_views.py     # 4. 角色视角生成
python3 cutout_from_sheet.py       # 5. 从 sprite sheet 逐帧抠图
```

## 添加新场景

1. `gen_assets.py` 添加 prompt
2. `gen_depth_lighting.py` 的 `SCENE_LIGHTS` 添加光源配置
3. `lighting-config.json` 添加实时渲染光源配置
4. `gen_masks.py` 添加物体 bbox + walkable + water
5. `index.html` SCENES 添加场景定义
6. `VFX.SCENE_CONFIG` 添加动效配置
7. 运行生成脚本
8. `git add -A && git commit && git push`

## 图片格式规范

**所有生成的图片素材必须为 WebP 格式。**

- 生成脚本输出 `.webp`
- `.gitignore` 已屏蔽 `.png`、`.jpg`、`.jpeg`、`.bmp`、`.gif`
- 例外：`preview_*.gif`（行走预览 GIF）
