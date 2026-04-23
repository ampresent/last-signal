# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置、依赖下载 — 从零到可开发。
>
> **核心原则**：深度模型通过 HuggingFace 镜像下载，本地推理。

---

## 一键初始化

```bash
cd /root/.openclaw/workspace/last-signal
bash setup.sh
```

自动完成 5 步：阿里云源 → PyTorch (R2) → pip 依赖 → HF 镜像配置 → 环境检查。

---

## 架构概览

| 组件 | 方式 | 说明 |
|------|------|------|
| 深度估计 | Depth-Anything-V2-Large (本地推理) | 通过 hf-mirror.com 下载，transformers pipeline |
| 图片生成 | Pollinations.AI | 免费文生图/图生图 |
| 帧渲染 | 本地 Python (NumPy + OpenCV) | 光照计算、光流插值 |
| 依赖 | `torch`, `transformers`, `timm`, `numpy`, `opencv-python-headless` | |

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

---

## 3. 安装 Python 依赖

### 3a. PyTorch (从 R2 桶下载，~182MB)

PyTorch CPU 版本从 Cloudflare R2 桶下载（比 CDN 快 3-5 倍）：

```bash
pip3 install --break-system-packages -q s3cmd

# 配置 R2 凭据（从 r2mount.py 自动提取）
python3 -c "
import re, pathlib
src = pathlib.Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
pathlib.Path(pathlib.Path.home() / '.s3cfg').write_text(f'''[default]
access_key = {ak}
secret_key = {sk}
host_base = {ep}
host_bucket = %(bucket)s.{ep}
use_https = True
''')
" && chmod 600 ~/.s3cfg

# 下载并安装 torch (182MB, ~6MB/s from R2)
s3cmd --region=auto get \
  s3://mystore/deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl --force

pip3 install --break-system-packages \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl

# 下载并安装 torchvision stub (5KB, 解决 ABI 不兼容)
s3cmd --region=auto get \
  s3://mystore/deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl \
  /tmp/torchvision-0.22.0+cpu.stub-py3-none-any.whl --force

pip3 install --break-system-packages --no-deps \
  /tmp/torchvision-0.22.0+cpu.stub-py3-none-any.whl
```

### 3b. 其余依赖

```bash
pip3 install --break-system-packages \
  transformers timm numpy opencv-python-headless requests pillow
```

### 3c. torchvision stub 补丁（重要！）

torchvision stub 缺少 transformers 5.x 需要的模块，需要手动补充：

```bash
# 1. 创建 torchvision.io stub
mkdir -p /usr/local/lib/python3.12/dist-packages/torchvision/io
cat > /usr/local/lib/python3.12/dist-packages/torchvision/io/__init__.py << 'STUB'
"""torchvision.io stub - placeholder for transformers compatibility."""
class ImageReadMode:
    UNCHANGED = 0; GRAY = 1; GRAY_ALPHA = 2; RGB = 3; RGB_ALPHA = 4
def decode_image(input, mode=ImageReadMode.UNCHANGED):
    raise NotImplementedError("torchvision.io stub")
STUB

# 2. 创建 torchvision.transforms.v2 stub
mkdir -p /usr/local/lib/python3.12/dist-packages/torchvision/transforms/v2
cat > /usr/local/lib/python3.12/dist-packages/torchvision/transforms/v2/__init__.py << 'STUB'
from torchvision.transforms import functional
STUB
cat > /usr/local/lib/python3.12/dist-packages/torchvision/transforms/v2/functional.py << 'STUB'
from torchvision.transforms.functional import *
STUB

# 3. 向 functional.py 添加缺失的函数和属性
python3 -c "
f = '/usr/local/lib/python3.12/dist-packages/torchvision/transforms/functional.py'
with open(f) as fh: content = fh.read()
# 添加 NEAREST_EXACT
content = content.replace(
    'NEAREST = \"nearest\"',
    'NEAREST = \"nearest\"\n    NEAREST_EXACT = \"nearest-exact\"'
)
# 添加 pil_to_tensor
content += '''
def pil_to_tensor(pic):
    if isinstance(pic, Image.Image):
        arr = np.array(pic)
        if arr.ndim == 2: arr = arr[np.newaxis, ...]
        else: arr = arr.transpose(2, 0, 1)
        return torch.from_numpy(arr.copy())
    raise TypeError(f\"Expected PIL Image, got {type(pic)}\")
'''
# 修复 resize 接受 antialias 参数
content = content.replace(
    'def resize(img, size, interpolation=InterpolationMode.BILINEAR):',
    'def resize(img, size, interpolation=InterpolationMode.BILINEAR, antialias=None):'
)
# 修复 resize 处理 3D tensor (C,H,W)
old = '''    if isinstance(img, torch.Tensor):
        return TF.interpolate(img.unsqueeze(0), size=size, mode=mode if mode != \"nearest\" else \"nearest\",
                              align_corners=False if mode not in (\"nearest\",) else None).squeeze(0)'''
new = '''    if isinstance(img, torch.Tensor):
        needs_squeeze = False
        if img.ndim == 3: img = img.unsqueeze(0); needs_squeeze = True
        mode_str = mode if mode != \"nearest\" else \"nearest\"
        result = TF.interpolate(img, size=size, mode=mode_str,
                                align_corners=False if mode_str not in (\"nearest\",) else None)
        if needs_squeeze: result = result.squeeze(0)
        return result'''
content = content.replace(old, new)
with open(f, 'w') as fh: fh.write(content)
print('Patched torchvision stub')
"
```

> **为什么需要这些补丁？**
> torch 2.11.0+cpu 是自定义构建，原生 torchvision C++ ABI 不兼容。stub 是纯 Python 实现，
> 但 transformers 5.x 额外依赖 `torchvision.io`、`torchvision.transforms.v2`、
> `pil_to_tensor`、`InterpolationMode.NEAREST_EXACT` 和 `resize(antialias=)` 等。
> setup.sh 中已包含自动补丁。

### 3d. 修复 torch 元数据（重要！）

torch `2.11.0+cpu` 的 dist-info 目录名含 `+cpu`，导致 `importlib.metadata` 无法解析版本号：

```bash
# 重命名 dist-info 并修复 METADATA
python3 -c "
import os, shutil
sp = '/usr/local/lib/python3.12/dist-packages'
old = f'{sp}/torch-2.11.0+cpu.dist-info'
new = f'{sp}/torch-2.11.0.dist-info'
if os.path.exists(new): shutil.rmtree(new)
os.rename(old, new)
meta = f'{new}/METADATA'
with open(meta) as f: content = f.read()
content = content.replace('Version: 2.11.0+cpu', 'Version: 2.11.0')
with open(meta, 'w') as f: f.write(content)
print('Fixed torch metadata')
"
```

> **症状**：`TypeError: expected string or bytes-like object, got 'NoneType'`
> **原因**：`importlib.metadata.version('torch')` 返回 `None`（dist-info 目录名含 `+cpu`）
> setup.sh 中已包含自动修复。

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

首次运行 `gen_apartment_lighting.py` 时会自动从镜像下载 Depth-Anything-V2-Large 模型（~1.3GB），
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

### gen_ai_frames.py 覆盖公寓帧

`gen_ai_frames.py` 会处理所有 8 个场景（包括公寓），用 img2img 帧覆盖 depth lighting 帧。
**解决方案：始终最后运行 `gen_apartment_lighting.py`。**

---

## 7. 依赖来源汇总

| 依赖 | 来源 | 大小 | 说明 |
|------|------|------|------|
| `torch-2.11.0+cpu` | R2 `s3://mystore/deps/` | 182MB | CPU-only wheel |
| `torchvision stub` | R2 `s3://mystore/deps/` | 5KB | 纯 Python，解决 ABI 问题 |
| `transformers` | PyPI (阿里云镜像) | ~30MB | HuggingFace 模型库 |
| `timm` | PyPI (阿里云镜像) | ~5MB | 视觉模型工具 |
| `numpy` | PyPI (阿里云镜像) | ~30MB | 数值计算 |
| `opencv-python-headless` | PyPI (阿里云镜像) | ~30MB | 图像处理 |
| `Depth-Anything-V2-Large` | hf-mirror.com | ~1.3GB | 深度估计模型（按需下载） |

---

*最后更新：2026-04-23*
