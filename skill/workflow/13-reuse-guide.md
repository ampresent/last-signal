# 复用指南

用这套引擎制作自己的 point & click 游戏：

## 步骤

1. **写剧情大纲** — 列出场景/物品/角色
2. **生成基础素材** — 修改 `gen_assets.py` 中的 PROMPTS 和 PORTRAITS
3. **配置光源** — 在 `gen_depth_lighting.py` 的 SCENE_LIGHTS 中添加光源配置
4. **配置交互** — 在 `gen_masks.py` 的 SCENES 中定义物体 bbox、walkable、water
5. **构建游戏逻辑** — 复制引擎代码，在 SCENES 中定义场景、对话、物品
6. **配置动效** — 在 VFX.SCENE_CONFIG 中添加粒子效果
7. **运行生成脚本** — 按顺序执行 gen_assets → gen_depth_lighting → gen_masks
8. **本地测试** — `python3 -m http.server 8765`
9. **推送部署** — `git add -A && git commit && git push`

## 最小可运行版本

只需要：
- 1 个场景 prompt（gen_assets.py）
- 1 个光源配置（gen_depth_lighting.py）
- 1 个场景定义（index.html SCENES）
- index.html 中的 Game 对象

不需要深度模型也能跑——去掉光照帧，直接用静态背景图。
