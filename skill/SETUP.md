# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置、依赖下载 — 从零到可开发。
>
> **核心原则**：大型依赖（torch wheel、模型权重）优先从 Cloudflare R2 拉取，国内镜像备选。

---

## 一键初始化

```bash
cd /root/.openclaw/workspace/last-signal
bash skill/scripts/setup.sh
```

自动完成 7 步：阿里云源 → pip 依赖 → MobileSAM 模型 → RMBG-1.4 模型 → HF 镜像 → git 配置 → 环境检查。

> **注意**：`setup.sh` 只装核心依赖（onnxruntime 等），**不装 torch/transformers**。
> torch 等大型包需手动从 R2 安装（见 §3b）。

---

## 从零复现指南（服务器重建 / 新机器部署）

> **前提**：只剩 GitHub 仓库 `ampresent/last-signal` 的远程状态是持久的。
> 所有本地文件（clone、模型、依赖、帧提取）都需要重建。
>
> **实测环境**：阿里云 ECS，3.4GB RAM，无 GPU，Python 3.12，2026-04-28 验证通过。

### 第一步：环境准备

```bash
# 写入 GitHub token
echo 'YOUR_GITHUB_TOKEN' > /root/.openclaw/workspace/.gh-token

# Clone 仓库（用 token 认证，保留完整 commit log）
cd /root/.openclaw/workspace
git clone https://YOUR_GITHUB_TOKEN@github.com/ampresent/last-signal.git
cd last-signal

# 切到 PR #46 分支（已 rebase 到 main 最新，包含 RMBG-1.4 抠图 + SETUP.md 改版）
git checkout feat/rmbg2-cutout

# 设置 git 身份（push 需要）
git config user.name "ampresent"
git config user.email "ampresent@users.noreply.github.com"
```

### 第二步：安装 Python 依赖

```bash
# pip 阿里源
cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF

# 核心依赖
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow

# PyTorch CPU 版（从 R2 下载，国内 PyPI 慢）
pip3 install --break-system-packages boto3
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
os.makedirs('/tmp/r2deps', exist_ok=True)
for key in ['deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl',
 'deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl']:
 fname = os.path.basename(key)
 dest = f'/tmp/r2deps/{fname}'
 if not os.path.exists(dest):
   s3.download_file('mystore', key, dest)
   print(f' {fname} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
pip3 install --break-system-packages --no-cache-dir /tmp/r2deps/torch-*.whl /tmp/r2deps/torchvision-*.whl

# transformers + timm + kornia（清华镜像快）
pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
  --ignore-installed rich transformers timm kornia
```

> **⚠️ kornia 是必须依赖**：`rmbg14_cutout.py` 内部依赖 kornia。
> 不装 kornia 会导致 `ModuleNotFoundError: No module named 'kornia'`。
>
> **⚠️ `--ignore-installed rich`**：Debian 预装的 rich 缺少 RECORD 文件，不加此 flag 会报错。

### 第三步：下载 RMBG-1.4 模型

**方案 A：从 R2 下载（快，推荐）**

```bash
cd /root/.openclaw/workspace/last-signal
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
os.makedirs('models/RMBG-1.4', exist_ok=True)
for f in ['model.safetensors', 'config.json', 'briarmbg.py', 'MyConfig.py', 'MyPipe.py', 'preprocessor_config.json', 'utilities.py']:
 dest = f'models/RMBG-1.4/{f}'
 if not os.path.exists(dest):
   s3.download_file('mystore', f'deps/RMBG-1.4/{f}', dest)
   print(f' {f} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
```

> 模型总计 ~169MB，R2 下载约 5s。7 个文件：`model.safetensors`（权重）、`config.json`、
> `briarmbg.py`、`MyConfig.py`、`MyPipe.py`、`preprocessor_config.json`、`utilities.py`。

**方案 B：从 HuggingFace 镜像下载（R2 不可用时）**

```bash
HF_ENDPOINT=https://hf-mirror.com python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='briaai/RMBG-1.4',
    local_dir='models/RMBG-1.4',
    ignore_patterns=['*.md', '*.txt', '.gitattributes'],
)
print('Done')
"
```

### 第四步：下载视频并提取帧

```bash
mkdir -p /tmp/sprite-work
curl -L -o /tmp/sprite-work/source.mov \
 "https://cnbj3-fusion.fds.api.xiaomi.com/...source.mov..."

mkdir -p /tmp/sprite-work/frames
ffmpeg -y -i /tmp/sprite-work/source.mov /tmp/sprite-work/frames/frame_%04d.png
```

### 第五步：裁剪后方向关键帧

```python
from PIL import Image
import os
os.makedirs('/tmp/sprite-work/up_selected', exist_ok=True)
keyframes = [45, 52, 60, 68, 76, 84, 92, 100]
for i, fid in enumerate(keyframes):
    img = Image.open(f'/tmp/sprite-work/frames/frame_{fid:04d}.png')
    cropped = img.crop((114, 226, 614, 1226))  # 500x1000, 角色中心
    cropped.save(f'/tmp/sprite-work/up_selected/frame_{i:04d}.png')
```

### 第六步：跑 RMBG-1.4 抠图

```bash
cd /root/.openclaw/workspace/last-signal
python3 skill/scripts/rmbg14_cutout.py up /tmp/sprite-work/up_selected --char kai --no-verify
```

> Sheet 模式更快（7.5x）：`--sheet` 参数拼成 4x2 大图，单次推理。
> 逐帧：~3.0s/帧 | Sheet：~0.4s/帧。

输出到 `assets/sprites/kai_up_f{0-7}.webp`（64×128 RGBA WebP）。

> **⚠️ 内存注意**：模型加载 + 推理峰值约 2-2.5GB。3.4GB 机器上可行，但别同时跑其他大进程。
> 如果被 SIGTERM 杀掉，检查 `free -h`，确保可用内存 > 2.5GB。

---

## 架构概览

| 组件 | 方式 | 说明 |
|------|------|------|
| 深度估计 | Depth-Anything-V2-Large (本地推理) | R2 预存模型，hf-mirror.com 备选 |
| 图片生成 | Pollinations.AI | 免费文生图/图生图 |
| 帧渲染 | 本地 Python (NumPy + OpenCV) | 光照计算、光流插值 |
| Mask 生成 | MobileSAM (ONNX) + mimo-omni | R2 预存 ONNX 模型 |
| 背景移除 | RMBG-1.4 | R2 预存模型，公开无需 token |
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
> 如果阿里云镜像超时，可用清华镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple/`

---

## 2. Clone 仓库

```bash
git clone https://github.com/ampresent/last-signal.git
```

凭据文件不入仓库，`.gitignore` 已配置排除 `.github-token`、`.hf-token`、`.s3cfg`。

---

## 3. 安装 Python 依赖

### 3a. 核心依赖

```bash
pip3 install --break-system-packages \
  onnxruntime numpy opencv-python-headless requests pillow
```

### 3b. PyTorch + Transformers（从 R2 安装）

**⚠️ torch 体积大（~182MB），PyPI/国内镜像下载慢。R2 预存了 CPU 版本，秒级拉取。**

```bash
# 配置 R2 凭据（如果还没有 ~/.s3cfg）
# 见下方 §8 R2 存储 章节

# 从 R2 下载 wheel
mkdir -p /tmp/r2deps
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
for key in ['deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl',
            'deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl']:
    fname = os.path.basename(key)
    dest = f'/tmp/r2deps/{fname}'
    if not os.path.exists(dest):
        print(f'Downloading {fname}...')
        s3.download_file('mystore', key, dest)
    print(f'  ✓ {fname} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"

# 安装 torch + torchvision stub
pip3 install --break-system-packages --no-cache-dir \
  /tmp/r2deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
  /tmp/r2deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl

# 安装 transformers + timm（从清华镜像，阿里云可能超时）
pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
  transformers timm
```

> **为什么用 torchvision stub？** torch 2.11.0+cpu 是自定义构建，原生 torchvision C++ ABI 不匹配。
> stub 版本是纯 Python，绕过 ABI 问题。见 §6 已知问题。

### 3c. RMBG-1.4 背景移除

用于从任意背景抠图。模型已预存 R2，公开模型无需 HF token。

```bash
# 依赖：torch + transformers（§3b 已装）
# 模型：从 R2 下载 (~169MB) 或 HuggingFace 镜像
# 用法：python3 scripts/rmbg14_cutout.py <direction> <frames_dir>
# Sheet 模式（更快）：python3 scripts/rmbg14_cutout.py <direction> <frames_dir> --sheet
```

### 3d. mimo-omni（可选，用于叠层验证）

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

> **hf-mirror.com 只提供模型下载，不提供 Serverless Inference API。**
> 如需使用 HF API，需要代理或 VPN。

---

## 5. 模型下载

### Depth-Anything-V2-Large（深度估计，~1.3GB）

**首选：从 R2 下载（国内快）**

```bash
python3 -c "
import boto3, re
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
import os; os.makedirs('models/depth-anything-v2-large-hf', exist_ok=True)
for key in ['models/depth-anything-v2-large-hf/config.json',
            'models/depth-anything-v2-large-hf/model.safetensors',
            'models/depth-anything-v2-large-hf/preprocessor_config.json']:
    fname = os.path.basename(key)
    dest = f'models/depth-anything-v2-large-hf/{fname}'
    if not os.path.exists(dest):
        print(f'Downloading {fname}...')
        s3.download_file('mystore', key, dest)
    print(f'  ✓ {fname} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
```

**备选：hf-mirror.com（R2 不可用时）**

首次运行 `gen_depth_lighting.py` 时自动从镜像下载，缓存到 `~/.cache/huggingface/`。

### MobileSAM ONNX（Mask 生成，~43MB）

**首选：从 R2 下载**

```bash
mkdir -p models
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
for key, dest in [('deps/mobilesam.encoder.onnx', 'models/mobilesam.encoder.onnx'),
                  ('deps/mobile_sam.onnx', 'models/mobile_sam.onnx')]:
    if not os.path.exists(dest):
        print(f'Downloading {os.path.basename(key)}...')
        s3.download_file('mystore', key, dest)
    print(f'  ✓ {dest} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
```

**备选：hf-mirror.com / setup.sh 自动下载**

```bash
# 手动下载
curl -L "https://hf-mirror.com/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx" \
  -o models/mobile_sam_vit_t.onnx

# 或运行 setup.sh 自动处理
bash skill/scripts/setup.sh
```

---

## 6. 环境检查

```bash
python3 -c "import torch; print(torch.__version__)"          # 2.11.0+cpu
python3 -c "import torchvision; print(torchvision.__version__)"  # 0.22.0+cpu-stub
python3 -c "import transformers; print(transformers.__version__)"
python3 -c "import timm; print(timm.__version__)"
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import numpy; print(numpy.__version__)"

# 测试 HF 镜像可达性
curl -s https://hf-mirror.com/api/models/depth-anything/Depth-Anything-V2-Large-hf \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','FAIL'))"
```

---

## 7. 已知问题与解决方案

### torch + torchvision ABI 不兼容

torch 2.11.0+cpu 是自定义构建版本，原生 torchvision C++ 扩展 ABI 不匹配。
**用 torchvision stub（纯 Python）解决**。见 §3b。

### torch 版本号 `+cpu` 导致 transformers 崩溃

`importlib.metadata` 无法解析 `2.11.0+cpu`。**重命名 dist-info 修复**：

```bash
# 找到 torch dist-info 目录
TORCH_DIR=$(python3 -c "import torch; print(torch.__path__[0])")
DIST_INFO=$(dirname "$TORCH_DIR")/torch-2.11.0+cpu.dist-info
if [ -d "$DIST_INFO" ]; then
  mv "$DIST_INFO" "$(dirname "$DIST_INFO")/torch-2.11.0.dist-info"
  echo "✓ Fixed: renamed dist-info to remove +cpu suffix"
fi
```

### HuggingFace 国内不可达

DNS 污染 + IP 封锁。**用 hf-mirror.com 下载模型**。见 §4。

### pip `externally-managed-environment`

Ubuntu 24.04 的 Python 被系统管理，所有 pip 命令需加 `--break-system-packages`。

### s3cmd `InvalidRegionName`

R2 必须 `--region=auto`，否则默认 US 区域名会报错。

### pip 镜像超时

阿里云镜像偶发超时。**备选清华镜像**：`-i https://pypi.tuna.tsinghua.edu.cn/simple/`

### rich 包冲突

Debian 预装的 `rich` 没有 RECORD 文件，pip 无法卸载。
**解决**：`--ignore-installed rich` 或 `--force-reinstall --no-deps rich` 后再装其他包。

### kornia 缺失导致 RMBG-1.4 加载失败

`rmbg14_cutout.py` 内部依赖 kornia。不装会报 `ModuleNotFoundError: No module named 'kornia'`。
**解决**：`pip3 install --break-system-packages kornia`（清华镜像快）。

### RMBG-1.4 推理被 SIGTERM 杀掉（OOM）

3.4GB 内存机器上，模型加载 + 推理峰值约 1.5-2GB。如果同时跑其他大进程可能 OOM。
**症状**：进程被 SIGTERM 杀掉，无报错。
**解决**：确保可用内存 > 2GB，关闭不必要的进程。`free -h` 检查。

### git push 超时 / GnuTLS recv error

国内到 GitHub 的 HTTPS 连接偶尔超时或 TLS 断开。
**解决**：重试即可，通常第二次能成功。如持续失败可尝试 SSH 或设置代理。

---

## 8. R2 存储

所有大型依赖预存在 Cloudflare R2，避免国内下载慢/不可达。

### 访问方式

```python
import boto3, re
from pathlib import Path

src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)

s3 = boto3.client('s3',
    endpoint_url='https://' + ep,
    aws_access_key_id=ak,
    aws_secret_access_key=sk,
    region_name='auto'
)
```

### R2 资源清单

| 路径 | 大小 | 说明 |
|------|------|------|
| `deps/torch-2.11.0+cpu-*.whl` | 181.5 MB | PyTorch CPU 版 (cp312) |
| `deps/torchvision-0.22.0+cpu-*.whl` | 1.9 MB | torchvision 匹配版 |
| `deps/torchvision-0.22.0+cpu.stub-*.whl` | <0.1 MB | torchvision 纯 Python stub |
| `deps/mobilesam.encoder.onnx` | 26.9 MB | MobileSAM encoder |
| `deps/mobile_sam.onnx` | 15.7 MB | MobileSAM decoder |
| `deps/FastSAM-x.pt` | 138.3 MB | FastSAM 模型 |
| `deps/wheels/numpy-*.whl` | 15.9 MB | numpy wheel |
| `deps/wheels/opencv_python_headless-*.whl` | 57.6 MB | OpenCV wheel |
| `deps/wheels/ultralytics-*.whl` | 1.2 MB | ultralytics (YOLO) |
| `models/depth-anything-v2-large-hf/` | ~1.3 GB | 深度估计模型（3 文件） |
| `deps/RMBG-1.4/` | ~169 MB | 背景移除模型（7 文件） |

### 上传新资源到 R2

```python
s3.upload_file('local_file.whl', 'mystore', 'deps/local_file.whl')
```

---

## 9. 依赖来源汇总

| 依赖 | 来源 | 大小 | 说明 |
|------|------|------|------|
| `torch` 2.11.0+cpu | **R2** `deps/` | 181.5 MB | PyTorch CPU 推理 |
| `torchvision` 0.22.0 stub | **R2** `deps/` | <0.1 MB | 纯 Python，绕 ABI 问题 |
| `transformers` | 清华镜像 PyPI | ~30 MB | HuggingFace 模型加载 |
| `timm` | 清华镜像 PyPI | ~5 MB | 视觉模型工具库 |
| `onnxruntime` | 阿里云 PyPI | ~15 MB | MobileSAM ONNX 推理 |
| `opencv-python-headless` | 阿里云 PyPI | ~30 MB | 图像处理 |
| `numpy` | 阿里云 PyPI | ~30 MB | 数值计算 |
| `pillow` | 阿里云 PyPI | ~3 MB | 图片读写 |
| `requests` | 阿里云 PyPI | ~50 KB | HTTP 请求 |
| MobileSAM ONNX | **R2** `deps/` | ~43 MB | Mask 生成模型 |
| Depth-Anything-V2-Large | **R2** `models/` | ~1.3 GB | 深度估计模型 |
| RMBG-1.4 | **R2** `deps/RMBG-1.4/` | ~169 MB | 背景移除模型 |

---

---

## 10. 抠图方案对比实验（2026-04-28）

在 3.4GB 内存 CPU 机器上实测，8帧 500×1000 → 64×128 RGBA WebP：

| 方案 | 耗时 | 内存峰值 | 说明 |
|------|------|----------|------|
| A: 逐帧推理（8次独立推理） | **8.4s** | ~2.5GB | ✅ 推荐 |
| B: 拼 4×2 sheet 单次推理 | 12.0s | ~2.5GB | ❌ 更慢 |

**为什么方案B更慢？**
- sheet 为 256×256，但模型内部 resize 到 1024×1024 处理
- 单张 sheet 的 1024×1024 推理 vs 8张 64×128 的推理，前者计算量更大
- 拆帧额外开销虽小（0.1s），但无法弥补推理差距

**结论：逐帧方案在 CPU 环境下更快、更稳定、内存更可控。不推荐拼 sheet。**

详细讨论见 `skill/workflow/07b-sprite-sheet.md` §6.5。

---

*最后更新：2026-04-28*
