# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置、依赖下载 — 从零到可开发。
>
> **核心原则**：深度模型通过 HuggingFace 镜像下载，本地推理。Mask 生成使用 MobileSAM (ONNX) + Omni 视觉模型。

---

## 一键初始化

```bash
cd /root/.openclaw/workspace/last-signal
bash setup.sh
```

自动完成 5 步：阿里云源 → pip 依赖 → MobileSAM 模型下载 → HF 镜像配置 → 环境检查。

---

## 架构概览

| 组件 | 方式 | 说明 |
|------|------|------|
| 深度估计 | Depth-Anything-V2-Large (本地推理) | 通过 hf-mirror.com 下载，transformers pipeline |
| 图片生成 | Pollinations.AI | 免费文生图/图生图 |
| 帧渲染 | 本地 Python (NumPy + OpenCV) | 光照计算、光流插值 |
| Mask 生成 | MobileSAM (ONNX) + mimo-omni | TinyViT 轻量分割 + 多模态视觉引导 + 叠层验证 |
| 依赖 | `onnxruntime`, `opencv-python-headless`, `numpy`, `pillow` | |

---

## 1. 阿里云软件源

### pip

```bash
cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
```

> 阿里云 ECS 出厂通常已预配。非阿里云机器需手动执行。

---

## 2. Clone 仓库

```bash
git clone https://github.com/ampresent/last-signal.git
```

凭据文件不入仓库，`.gitignore` 已配置排除 `.github-token`、`.hf-token`、`.s3cfg`。

### Git LFS (必须)

仓库的图片素材 (`.webp`, `.png`, `.gif`, `.pdf`) 通过 Git LFS 存储。
**clone 后必须拉取 LFS 文件**，否则图片为空壳指针：

```bash
# 安装 git-lfs (如果没有)
# 国内用 ghproxy 代理下载
curl -sL "https://ghfast.top/https://github.com/git-lfs/git-lfs/releases/download/v3.5.1/git-lfs-linux-amd64-v3.5.1.tar.gz" \
  | tar xz && cp git-lfs-3.5.1/git-lfs /usr/local/bin/ && chmod +x /usr/local/bin/git-lfs

# 初始化 + 拉取
git lfs install
git lfs pull
```

> **⚠️ 国内 GitHub 直连很慢**，`git lfs pull` 可能需要数分钟。
> 如果卡住，可尝试设置代理或使用 `ghfast.top` 加速。
> 也可只拉取需要的文件：`git lfs pull --include="assets/bg_apartment.webp"`

---

## 3. 安装 Python 依赖

### 3a. 核心依赖

```bash
pip3 install --break-system-packages \
  onnxruntime numpy opencv-python-headless requests pillow
```

### 3b. MobileSAM ONNX 模型

模型在首次运行 `gen_masks.py` 时自动从 hf-mirror.com 下载 (~2MB)。
也可手动下载：

```bash
mkdir -p models
# 优先 hf-mirror.com (国内快)
curl -L "https://hf-mirror.com/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx" \
  -o models/mobile_sam_vit_t.onnx

# 或 HuggingFace 原站
# curl -L "https://huggingface.co/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx" \
#   -o models/mobile_sam_vit_t.onnx
```

### 3c. mimo-omni (可选, 用于叠层验证)

Omni 视觉模型通过 OpenClaw skill 调用 (`~/.openclaw/skills/mimo-omni/mimo_api.sh`)。
如果不可用，`gen_masks.py` 会跳过 Omni 识别和验证步骤，仍能正常运行。

---

## 4. HuggingFace 镜像配置

**⚠️ 国内服务器（阿里云 ECS 等）无法直接访问 huggingface.co！**

DNS 会解析到 Facebook IP，连接超时。`hf-mirror.com` 是国内公益镜像站，支持模型下载。

```bash
# 设置环境变量（永久生效）
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
source ~/.bashrc

# 验证
curl -s https://hf-mirror.com/api/models/depth-anything/Depth-Anything-V2-Large-hf | head -1
```

首次运行 `gen_depth_lighting.py` 时会自动从镜像下载 Depth-Anything-V2-Large 模型（~1.3GB），
下载后缓存到 `~/.cache/huggingface/`，后续运行跳过（~3s 加载）。

> **hf-mirror.com 只提供模型下载，不提供 Serverless Inference API。**
> 如需使用 HF API，需要配置代理或 VPN。

---

## 5. 环境检查

```bash
python3 -c "import torch; print(torch.__version__)"          # 2.11.0+cpu
python3 -c "import torchvision; print(torchvision.__version__)"  # 0.22.0+cpu-stub
python3 -c "import transformers; print(transformers.__version__)"
python3 -c "import timm; print(timm.__version__)"
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import numpy; print(numpy.__version__)"

# 测试 HF 镜像可达性
curl -s https://hf-mirror.com/api/models/depth-anything/Depth-Anything-V2-Large-hf | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','FAIL'))"
```

---

## 6. 已知问题与解决方案

### torch + torchvision ABI 不兼容

torch 2.11.0+cpu 是自定义构建版本，原生 torchvision C++ 扩展 ABI 不匹配。
**用 torchvision stub（纯 Python）解决**。见 §3c。

### torch 版本号 `+cpu` 导致 transformers 崩溃

`importlib.metadata` 无法解析 `2.11.0+cpu`。**重命名 dist-info 修复**。见 §3d。

### HuggingFace 国内不可达

DNS 污染 + IP 封锁。**用 hf-mirror.com 下载模型**。见 §4。

### pip `externally-managed-environment`

Ubuntu 24.04 的 Python 被系统管理，所有 pip 命令需加 `--break-system-packages`。

### s3cmd `InvalidRegionName`

R2 必须 `--region=auto`，否则默认 US 区域名会报错。

### `git lfs pull` 国内卡住

GitHub LFS endpoint 在国内访问极慢。解决方案：
- 使用 `ghfast.top` 代理下载 git-lfs 二进制（见 §2）
- 设置 git 代理：`git config --global http.proxy <your-proxy>`
- 只拉需要的文件：`git lfs pull --include="assets/bg_apartment.webp"`
- 或将 LFS 存储迁移到 R2 等国内可达的对象存储

### ~~gen_ai_frames.py 覆盖公寓帧~~

> **已解决**：img2img 策略已完全移除，所有场景统一使用 `gen_depth_lighting.py`。

---

## 7. 依赖来源汇总

| 依赖 | 来源 | 大小 | 说明 |
|------|------|------|------|
| `git-lfs` | GitHub (ghproxy 代理) | ~5MB | Git 大文件存储，拉取图片素材 |
| `onnxruntime` | PyPI (阿里云镜像) | ~15MB | MobileSAM ONNX 推理引擎 |
| `opencv-python-headless` | PyPI (阿里云镜像) | ~30MB | 图像处理 + GrabCut 降级 |
| `numpy` | PyPI (阿里云镜像) | ~30MB | 数值计算 |
| `pillow` | PyPI (阿里云镜像) | ~3MB | 图片读写 |
| `requests` | PyPI (阿里云镜像) | ~50KB | HTTP 请求 |
| `mobile_sam_vit_t.onnx` | hf-mirror.com | ~2MB | MobileSAM TinyViT 模型权重 |
| `Depth-Anything-V2-Large` | hf-mirror.com | ~1.3GB | 深度估计模型（按需下载） |

---

*最后更新：2026-04-28*
