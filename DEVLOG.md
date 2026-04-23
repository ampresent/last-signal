# DEVLOG.md - 动画帧重制开发日志

## 2026-04-23 00:43 — 项目启动

### 环境
- 仓库已 clone，完整 commit log 保留
- 8 个场景 × 12 帧 = 96 帧已存在于 assets/

### 计划
1. **Phase 0**: 运行 setup.sh 安装依赖（torch, transformers, timm, opencv, 模型权重）
2. **Phase 1**: 公寓场景 — Depth Lighting (gen_apartment_lighting.py)

### 关键发现
- 公寓场景用策略 B（确定性 depth-based lighting），因为 img2img 帧间一致性差
- 其他场景用策略 A（img2img 关键帧 + OpenCV Farneback 光流插值）
- 需要从 R2 下载 ~2.8GB 的模型和依赖

### 当前步骤
- [x] Clone 仓库
- [ ] 安装依赖 (setup.sh)
- [ ] 重制公寓帧
- [ ] 重制其他场景帧
