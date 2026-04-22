#!/usr/bin/env bash
# setup.sh — 一键初始化 last-signal 开发环境
# 用法: bash setup.sh [项目目录]
#   默认项目目录: /root/.openclaw/workspace/last-signal
#
# R2 桶依赖：
#   s3://mystore/deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
#   s3://mystore/deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl
#   s3://mystore/depth_anything_v2_vitl.pth
#   s3://mystore/models/depth-anything-v2-large-hf/{config.json,preprocessor_config.json,model.safetensors}
#   s3://mystore/scripts/setup.sh  (本脚本自身)
set -euo pipefail

PROJECT="${1:-/root/.openclaw/workspace/last-signal}"
cd "$PROJECT"
echo "📁 项目目录: $(pwd)"

# ──────────────────────────────────────────────
# 0. 阿里云软件源（pip + apt）
# ──────────────────────────────────────────────
echo "=== [0/7] 阿里云软件源 ==="

if ! grep -q 'mirrors.aliyun.com/pypi' /etc/pip.conf 2>/dev/null; then
  cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
  echo "  ✓ pip 阿里云源"
else
  echo "  ✓ pip 已配，跳过"
fi

if ! grep -q 'mirrors.cloud.aliyuncs.com' /etc/apt/sources.list 2>/dev/null; then
  CODENAME=$(lsb_release -cs 2>/dev/null || echo "noble")
  cat > /etc/apt/sources.list << EOF
deb http://mirrors.cloud.aliyuncs.com/ubuntu ${CODENAME} main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu ${CODENAME}-updates main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu ${CODENAME}-backports main restricted universe multiverse
deb http://mirrors.cloud.aliyuncs.com/ubuntu ${CODENAME}-security main restricted universe multiverse
EOF
  apt-get update -qq 2>/dev/null || true
  echo "  ✓ apt 阿里云源"
else
  echo "  ✓ apt 已配，跳过"
fi

# ──────────────────────────────────────────────
# 1. s3cmd + R2 凭据（从 r2mount.py 自动提取）
# ──────────────────────────────────────────────
echo "=== [1/7] s3cmd + R2 凭据 ==="

pip3 install --break-system-packages -q s3cmd 2>/dev/null

if [ ! -f ~/.s3cfg ] || ! s3cmd --region=auto ls >/dev/null 2>&1; then
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
"
  chmod 600 ~/.s3cfg
  echo "  ✓ ~/.s3cfg 写入"
else
  echo "  ✓ ~/.s3cfg 已存在"
fi

s3cmd --region=auto ls | grep -q mystore && echo "  ✓ R2 连接正常"

# ──────────────────────────────────────────────
# 2. PyTorch CPU（R2，~182MB，6MB/s vs CDN 极慢）
# ──────────────────────────────────────────────
echo "=== [2/7] PyTorch CPU ==="

TORCH_WHL="torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl"
if ! python3 -c "import torch; assert torch.__version__ == '2.11.0+cpu'" 2>/dev/null; then
  s3cmd --region=auto get "s3://mystore/deps/${TORCH_WHL}" "/tmp/${TORCH_WHL}" --force 2>/dev/null
  pip3 install --break-system-packages -q "/tmp/${TORCH_WHL}" 2>/dev/null
  echo "  ✓ torch $(python3 -c 'import torch; print(torch.__version__)')"
else
  echo "  ✓ torch 已安装"
fi

# ──────────────────────────────────────────────
# 3. torchvision stub（R2，5KB wheel，解决 ABI 不兼容）
# ──────────────────────────────────────────────
echo "=== [3/7] torchvision stub ==="

STUB_WHL="torchvision-0.22.0+cpu.stub-py3-none-any.whl"
if ! python3 -c "import torchvision" 2>/dev/null; then
  # 清理可能残留的原生 torchvision
  pip3 uninstall -y torchvision 2>/dev/null || true
  rm -rf /usr/local/lib/python3.12/dist-packages/torchvision* 2>/dev/null

  s3cmd --region=auto get "s3://mystore/deps/${STUB_WHL}" "/tmp/${STUB_WHL}" --force 2>/dev/null
  pip3 install --break-system-packages --no-deps "/tmp/${STUB_WHL}" 2>/dev/null
  echo "  ✓ torchvision $(python3 -c 'import torchvision; print(torchvision.__version__)')"
else
  echo "  ✓ torchvision 已安装"
fi

# ──────────────────────────────────────────────
# 4. 其余 Python 依赖（阿里云 PyPI，快）
# ──────────────────────────────────────────────
echo "=== [4/7] Python 依赖 ==="

pip3 install --break-system-packages -q \
  numpy opencv-python-headless transformers timm 2>/dev/null

echo "  ✓ $(python3 -c 'import numpy,cv2,transformers,timm; print(f"numpy {numpy.__version__}, cv2 {cv2.__version__}, transformers {transformers.__version__}, timm {timm.__version__}")')"

# ──────────────────────────────────────────────
# 5. 模型文件（R2 并行下载）
# ──────────────────────────────────────────────
echo "=== [5/7] 模型文件 ==="

mkdir -p models models/depth-anything-v2-large-hf

NEED_ORIG=false; NEED_HF=false
[ ! -f models/depth_anything_v2_vitl.pth ] && NEED_ORIG=true
[ ! -f models/depth-anything-v2-large-hf/model.safetensors ] && NEED_HF=true

if $NEED_ORIG; then
  s3cmd --region=auto get s3://mystore/depth_anything_v2_vitl.pth \
    models/depth_anything_v2_vitl.pth --force 2>/dev/null &
  echo "  ↓ DA2 原始权重 (~1.3GB) 下载中..."
fi

if $NEED_HF; then
  for f in config.json preprocessor_config.json model.safetensors; do
    s3cmd --region=auto get \
      "s3://mystore/models/depth-anything-v2-large-hf/$f" \
      "models/depth-anything-v2-large-hf/$f" --force 2>/dev/null &
  done
  echo "  ↓ DA2 transformers 权重 (~1.3GB) 下载中..."
fi

if $NEED_ORIG || $NEED_HF; then
  wait
  echo "  ✓ 模型下载完成"
else
  echo "  ✓ 模型已存在"
fi

# ──────────────────────────────────────────────
# 6. git 配置
# ──────────────────────────────────────────────
echo "=== [6/7] git 配置 ==="

# 凭据文件不入仓库
echo ".git-credentials-file" >> .gitignore 2>/dev/null || true
echo ".github-token" >> .gitignore 2>/dev/null || true
echo ".s3cfg" >> .gitignore 2>/dev/null || true
git add .gitignore 2>/dev/null && git commit -m "chore: ignore credential files" --allow-empty 2>/dev/null || true

echo "  ✓ .gitignore 已更新"

# ──────────────────────────────────────────────
# 7. 环境检查
# ──────────────────────────────────────────────
echo "=== [7/7] 环境检查 ==="
ERR=0
check() { python3 -c "$1" 2>/dev/null && echo "  ✓ $2" || { echo "  ✗ $2 FAILED"; ERR=$((ERR+1)); }; }

check "import torch; assert torch.__version__=='2.11.0+cpu'" "torch 2.11.0+cpu"
check "import torchvision; print(torchvision.__version__)" "torchvision stub"
check "import transformers" "transformers $(python3 -c 'import transformers; print(transformers.__version__)' 2>/dev/null)"
check "import timm" "timm $(python3 -c 'import timm; print(timm.__version__)' 2>/dev/null)"
check "import cv2" "opencv $(python3 -c 'import cv2; print(cv2.__version__)' 2>/dev/null)"
check "import numpy" "numpy $(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null)"

[ $(git log --oneline 2>/dev/null | wc -l) -ge 1 ] && echo "  ✓ git repo" || { echo "  ✗ git repo"; ERR=$((ERR+1)); }
s3cmd --region=auto ls 2>/dev/null | grep -q mystore && echo "  ✓ R2 connection" || { echo "  ✗ R2"; ERR=$((ERR+1)); }
[ -f models/depth_anything_v2_vitl.pth ] && echo "  ✓ DA2 original $(du -h models/depth_anything_v2_vitl.pth | cut -f1)" || { echo "  ✗ DA2 original missing"; ERR=$((ERR+1)); }
[ -f models/depth-anything-v2-large-hf/model.safetensors ] && echo "  ✓ DA2 HF $(du -h models/depth-anything-v2-large-hf/model.safetensors | cut -f1)" || { echo "  ✗ DA2 HF missing"; ERR=$((ERR+1)); }

echo ""
if [ $ERR -eq 0 ]; then
  echo "🎉 全部通过，环境就绪！"
else
  echo "⚠️  ${ERR} 项检查失败，请查看上方输出"
  exit 1
fi
