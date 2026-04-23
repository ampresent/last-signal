# DEVLOG.md - 动画帧重制开发日志

## 2026-04-23 00:43 — 项目启动

### 环境
- 仓库已 clone，完整 commit log 保留
- 8 个场景 × 12 帧 = 96 帧已存在于 assets/

### 计划
1. **Phase 0**: 运行 setup.sh 安装依赖（torch, transformers, timm, opencv, 模型权重）
2. **Phase 1**: 公寓场景 — Depth Lighting (gen_apartment_lighting.py)

### 当前步骤
- [x] Clone 仓库
- [x] 安装依赖 (setup.sh) — 全部通过
- [ ] 重制公寓帧

---

## 2026-04-23 11:08 — 代码审查：发现的问题

对照 `docs/superpowers/specs/2026-04-22-apartment-depth-lighting-design.md` 和现有实现 `gen_apartment_lightning.py`，发现以下问题：

### 🔴 P0 — 阻塞性问题

#### 1. 缺少 Depth-Anything-V2 模型代码仓库
- **设计文档要求**：Clone `https://github.com/DepthAnything/Depth-Anything-V2` 获取 `depth_anything_v2/dpt.py`
- **现有实现**：`REPO_DIR = Path(__file__).parent / "depth_anything_v2_repo"`，但该目录不存在
- **setup.sh**：没有 clone 这个仓库的步骤
- **影响**：脚本直接 crash（`ModuleNotFoundError`），完全无法运行
- **修复**：在 setup.sh 中添加 clone Depth-Anything-V2 repo 的步骤，或改用 transformers/timm fallback

#### 2. 文件名拼写错误
- **设计文档**：`gen_apartment_lighting.py`
- **实际文件**：gen_apartment_light**n**ing.py（多了个 `n`）
- **影响**：WORKFLOW.md、SETUP.md 引用的都是 `lighting`，对不上
- **修复**：重命名文件

### 🟡 P1 — 逻辑偏差

#### 3. 无模型加载 fallback
- **设计文档**：3 级 fallback（official → timm → transformers）
- **实现**：只有 official 一种路径，无 fallback
- **影响**：一旦模型路径变了就直接挂

#### 4. 循环不无缝（数学错误）
- **设计文档声称**："f0 == f12，循环无缝"
- **实际数学**：`intensity = min + (max-min) * (0.5 + 0.5 * sin(2π * frame/12 + phase))`
  - f0: sin(0) = 0 → intensity = min + (max-min) * 0.5
  - f11: sin(2π * 11/12) = sin(11π/6) ≈ -0.5 → intensity = min + (max-min) * 0.25
  - f0 ≠ f11，首尾帧不同，loop 会有跳变
- **修复**：应该用 `sin(2π * frame/12)` 且确保 frame=0 和 frame=12 一致（frame 取 0~11，共 12 帧，第 12 帧 = 第 0 帧）

#### 5. Shadow ray march 步数不一致
- **设计文档**：64 步
- **实现**：48 步
- **影响**：性能和质量的 trade-off，48 步可能在某些角度产生阴影伪影

#### 6. 合成方式不一致
- **设计文档**：additive blending（叠加光照）
- **实现**：multiplicative blending（`base * lighting`）
- **影响**：乘法合成会让暗部更暗、整体偏暗；加法合成保持原图亮度并叠加光晕
- **注**：乘法方式在实际效果上可能也 OK，但与设计文档不符

### 🟢 P2 — 小问题

#### 7. `torch.nn.functional` 导入未使用
- 代码中 `import torch.nn.functional as F` 但从未使用

#### 8. setup.sh 缺少 Depth-Anything-V2 repo 下载
- 即使不修 fallback，至少需要 clone 模型代码仓库

---

## 修复计划

1. ✅ 先 push 这份 DEVLOG（记录问题）
2. Clone Depth-Anything-V2 repo（或改用 transformers fallback）
3. 修复文件名 typo
4. 修复循环数学
5. 统一合成方式（按设计文档用 additive）
6. 运行生成帧
7. 验证 + push

---

## 2026-04-23 16:51 — 架构变更：本地模型 → HuggingFace Serverless Inference API

### 变更原因
用户要求不再本地部署 Depth Anything 模型，改为调用 HuggingFace Serverless Inference API。这样：
- 无需下载 1.3GB 模型权重
- 无需安装 torch/torchvision（省 ~182MB wheel + 编译时间）
- 无需 R2 桶的模型存储
- 无需 CPU 占用率限制（计算在远端）
- 依赖大幅减少：只需 `requests`、`opencv-python-headless`、`numpy`

### 发现的新问题

#### 🔴 P0 — 架构变更相关

##### 1. setup.sh 安装了大量不再需要的依赖
- **现状**：setup.sh 安装 torch (182MB)、torchvision stub、s3cmd、R2 凭据
- **改为 API 后**：只需 `requests`、`opencv-python-headless`、`numpy`
- **修复**：重写 setup.sh，移除 torch/torchvision/s3cmd/R2 相关步骤

##### 2. gen_apartment_lightning.py 整个模型加载逻辑需要重写
- **现状**：3 级 fallback（official repo → transformers → timm），全部本地加载
- **改为 API 后**：发送图片到 HF Inference API，接收深度图
- **修复**：重写 `load_depth_model()` 和 `generate_depth_map()` 为 API 调用

##### 3. CPU 占用率限制代码不再需要
- **现状**：`CPU_LIMIT = 0.95`、`FRAME_SLEEP = 0.05`、`nice`/`chrt` 调度
- **改为 API 后**：深度估计在远端，本地只有帧渲染（很快）
- **修复**：移除 CPU 限制相关代码和文档

##### 4. SETUP.md 中 R2 模型下载部分不再需要
- **现状**：详细的 R2 模型下载说明（1.3GB）
- **改为 API 后**：模型在 HuggingFace 端
- **修复**：重写 SETUP.md，移除 R2 模型部分

##### 5. 文件名拼写错误仍未修复
- **现状**：`gen_apartment_lightning.py`（多一个 `n`）
- **影响**：WORKFLOW.md、SETUP.md 引用 `lighting`，文件名是 `lightning`
- **修复**：重命名文件

#### 🟡 P1 — 需要确认

##### 6. HuggingFace API Token
- **问题**：调用 HF Serverless Inference API 需要 API Token
- **现状**：项目中没有 HF Token 配置
- **需要**：用户提供 HF Token，或确认使用免费无需 Token 的端点

---

## 修复计划（更新）

1. ✅ Push DEVLOG（记录问题）
2. 确认 HF API Token 需求
3. 重写 setup.sh（移除 torch/s3cmd/R2，添加 requests）
4. 重写 SETUP.md（API 方式说明）
5. 重写 gen_apartment_lightning.py（API 调用 + 移除 CPU 限制）
6. 修复文件名 typo
7. 更新 docs（移除 CPU 限制说明）
8. 运行生成帧
9. 验证 + push
