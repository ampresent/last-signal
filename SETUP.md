# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置、依赖下载 — 从零到可开发。
>
> **核心原则**：一切能从 R2 桶获取的，不走外网。

---

## 一键初始化

```bash
cd /root/.openclaw/workspace/last-signal
bash setup.sh
```

自动完成 6 步：阿里云源 → s3cmd + R2 → PyTorch → torchvision stub → pip 依赖 → git 配置。模型文件按需下载，不随初始化安装。

---

## R2 桶全景 (`s3://mystore`)

| 路径 | 大小 | 来源 | 用途 |
|------|------|------|------|
| **deps/** | | | Python 依赖（R2 缓存） |
| `deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` | 182MB | 自构建 | PyTorch CPU wheel |
| `deps/torchvision-0.22.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` | 2.0MB | PyTorch CDN 备份 | 原生 wheel（ABI 不兼容，备用） |
| `deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl` | 5KB | 本机构建 | **纯 Python stub**，解决 torch 2.11.0 ABI 问题 |
| **models/** | | | 模型权重（按需下载，不随 setup.sh） |
| `depth_anything_v2_vitl.pth` | 1.3GB | R2 原始 | DA2-Large 原始权重 |
| `models/depth-anything-v2-large-hf/model.safetensors` | 1.3GB | R2 原始 | DA2-Large transformers 权重 |
| `models/depth-anything-v2-large-hf/config.json` | 1KB | R2 原始 | transformers 配置 |
| `models/depth-anything-v2-large-hf/preprocessor_config.json` | 1KB | R2 原始 | 预处理配置 |
| **scripts/** | | | 工具脚本 |
| `scripts/setup.sh` | 13KB | 本机上传 | 一键初始化脚本 |

**总计：~2.8GB**

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

### apt (Ubuntu 24.04 Noble)

```bash
cat > /etc/apt/sources.list << 'EOF'
deb http://mirrors.cloud.aliyuncs.com/ubuntu noble main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu noble-updates main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu noble-backports main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu noble-security main restricted universe multiverse
EOF
apt-get update
```

> 阿里云 ECS 出厂通常已预配。非阿里云机器需手动执行。

---

## 2. Clone 仓库

```bash
git -c credential.helper='store --file=/path/to/.git-credentials-file' \
  clone https://github.com/ampresent/last-signal.git
```

---

## 3. s3cmd + R2 凭据

凭据在 `./r2mount.py`，自动写入 `~/.s3cfg`：

```bash
pip3 install --break-system-packages s3cmd

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

# 验证（必须 --region=auto）
s3cmd --region=auto ls   # 应看到 s3://mystore
```

---

## 4. 安装 Python 依赖

### 顺序：torch 先装 → 再装其余

```bash
# 从 R2 装 torch（~182MB，6MB/s，CDN 要 20min+）
s3cmd --region=auto get \
  s3://mystore/deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
  /tmp/

pip3 install --break-system-packages \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl

# 从 R2 装 torchvision stub（5KB，解决 ABI 不兼容）
s3cmd --region=auto get \
  s3://mystore/deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl \
  /tmp/

pip3 install --break-system-packages --no-deps \
  /tmp/torchvision-0.22.0+cpu.stub-py3-none-any.whl

# 其余从阿里云 PyPI 装（快）
pip3 install --break-system-packages \
  numpy opencv-python-headless transformers timm
```

### torchvision stub 说明

torch 2.11.0+cpu 和原生 torchvision C++ ABI 不兼容：
- `RuntimeError: operator torchvision::nms does not exist`
- `Segmentation fault (core dumped)`

**stub 是纯 Python 实现**，提供 timm 所需的 `FrozenBatchNorm2d`、`ToTensor`、`InterpolationMode` 等接口。无需 C++ 扩展，兼容任意 torch 版本。

---

## 5. 模型文件（按需下载）

> **模型不在 setup.sh 中下载。** 各脚本（如 `gen_apartment_lightning.py`）运行时会自动检测，
> 缺失则从 R2 桶按需拉取，下载完成后缓存到本地，后续运行跳过。

首次运行某个需要模型的脚本时，会自动触发下载。也可手动预拉取：

```bash
mkdir -p models models/depth-anything-v2-large-hf

# 仅当需要原始 .pth 权重时（gen_apartment_lightning.py 等）
[ ! -f models/depth_anything_v2_vitl.pth ] && \
  s3cmd --region=auto get s3://mystore/depth_anything_v2_vitl.pth models/depth_anything_v2_vitl.pth

# 仅当需要 transformers 权重时（HuggingFace fallback 路径）
[ ! -f models/depth-anything-v2-large-hf/model.safetensors ] && \
  s3cmd --region=auto get s3://mystore/models/depth-anything-v2-large-hf/model.safetensors \
    models/depth-anything-v2-large-hf/model.safetensors
```

R2 桶中还存有 `config.json` 和 `preprocessor_config.json`，transformers fallback 路径需要时可一并拉取。

---

## 6. 环境检查

```bash
python3 -c "import torch; print(torch.__version__)"          # 2.11.0+cpu
python3 -c "import torchvision; print(torchvision.__version__)"  # 0.22.0+cpu-stub
python3 -c "import transformers; print(transformers.__version__)"
python3 -c "import timm; print(timm.__version__)"
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import numpy; print(numpy.__version__)"
```

模型文件按需下载，此处不检查。

---

## 7. 已知问题

### torch + torchvision ABI 不兼容

torch 2.11.0+cpu 是自定义构建版本，原生 torchvision C++ 扩展与其 ABI 不匹配。**用 stub 解决**。等官方发布匹配版本后可替换。

### pip `externally-managed-environment`

Ubuntu 24.04 的 Python 被系统管理，所有 pip 命令需加 `--break-system-packages`。

### s3cmd `InvalidRegionName`

R2 必须 `--region=auto`，否则默认 US 区域名会报错。

---

*最后更新：2026-04-22*
