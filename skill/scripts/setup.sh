#!/usr/bin/env bash
# setup.sh — 一键初始化 last-signal 开发环境
# 用法: bash setup.sh [项目目录]
#   默认项目目录: /root/.openclaw/workspace/last-signal
#
# 依赖：onnxruntime, opencv-python-headless, numpy, pillow, requests
# Mask 生成：MobileSAM (ONNX) + mimo-omni 视觉模型
# 深度模型：通过 HuggingFace 镜像下载，本地推理
set -euo pipefail

PROJECT="${1:-/root/.openclaw/workspace/last-signal}"
cd "$PROJECT"
echo "📁 项目目录: $(pwd)"

# ──────────────────────────────────────────────
# 0. 阿里云软件源（pip）
# ──────────────────────────────────────────────
echo "=== [0/6] 阿里云软件源 ==="

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

# ──────────────────────────────────────────────
# 1. Python 依赖
# ──────────────────────────────────────────────
echo "=== [1/6] Python 依赖 ==="

pip3 install --break-system-packages -q \
  requests numpy opencv-python-headless pillow onnxruntime 2>/dev/null

echo "  ✓ $(python3 -c 'import requests,cv2,numpy,onnxruntime; print(f"requests {requests.__version__}, cv2 {cv2.__version__}, numpy {numpy.__version__}, ort {onnxruntime.__version__}")')"

# ──────────────────────────────────────────────
# 2. MobileSAM ONNX 模型 (从 R2 下载, 国内快)
# ──────────────────────────────────────────────
echo "=== [2/6] MobileSAM ONNX 模型 ==="

SAM_ENCODER="$PROJECT/models/mobilesam.encoder.onnx"
SAM_DECODER="$PROJECT/models/mobile_sam.onnx"
SAM_OK=true

if [ -f "$SAM_ENCODER" ] && [ -f "$SAM_DECODER" ]; then
  echo "  ✓ MobileSAM 已存在 (encoder $(du -h "$SAM_ENCODER" | cut -f1), decoder $(du -h "$SAM_DECODER" | cut -f1))"
else
  mkdir -p "$PROJECT/models"

  # 配置 s3cmd (R2)
  if ! [ -f ~/.s3cfg ]; then
    python3 -c "
import re, pathlib
src = pathlib.Path('$PROJECT/r2mount.py').read_text()
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
  fi

  echo "  ⬇️  从 R2 下载 MobileSAM..."
  # encoder (27MB)
  if ! [ -f "$SAM_ENCODER" ]; then
    s3cmd --region=auto get s3://mystore/deps/mobilesam.encoder.onnx "$SAM_ENCODER" --force 2>/dev/null
    if [ -s "$SAM_ENCODER" ]; then
      echo "  ✓ encoder ($(du -h "$SAM_ENCODER" | cut -f1))"
    else
      echo "  ❌ encoder 下载失败"; SAM_OK=false
    fi
  fi
  # decoder (16MB)
  if ! [ -f "$SAM_DECODER" ]; then
    s3cmd --region=auto get s3://mystore/deps/mobile_sam.onnx "$SAM_DECODER" --force 2>/dev/null
    if [ -s "$SAM_DECODER" ]; then
      echo "  ✓ decoder ($(du -h "$SAM_DECODER" | cut -f1))"
    else
      echo "  ❌ decoder 下载失败"; SAM_OK=false
    fi
  fi

  if $SAM_OK; then
    echo "  ✓ MobileSAM 就绪"
  else
    echo "  ❌ MobileSAM 下载不完整, gen_masks.py 将无法运行"
  fi
fi

# ──────────────────────────────────────────────
# 3. Git LFS (大文件支持)
# ──────────────────────────────────────────────
echo "=== [3/6] Git LFS ==="

if command -v git-lfs &>/dev/null || command -v git-lfs &>/dev/null; then
  echo "  ✓ git-lfs 已安装 ($(git lfs version 2>/dev/null | head -1))"
else
  echo "  ⬇️  安装 git-lfs..."
  # 国内 GitHub 下载慢，用 ghproxy 代理
  GHTMP=$(mktemp -d)
  if curl -sL -o "$GHTMP/git-lfs.tar.gz" \
    "https://ghfast.top/https://github.com/git-lfs/git-lfs/releases/download/v3.5.1/git-lfs-linux-amd64-v3.5.1.tar.gz" \
    --connect-timeout 15 --max-time 120 2>/dev/null; then
    tar xzf "$GHTMP/git-lfs.tar.gz" -C "$GHTMP"
    cp "$GHTMP/git-lfs-3.5.1/git-lfs" /usr/local/bin/git-lfs
    chmod +x /usr/local/bin/git-lfs
    rm -rf "$GHTMP"
    echo "  ✓ git-lfs 安装完成 ($(git lfs version 2>/dev/null | head -1))"
  else
    rm -rf "$GHTMP"
    echo "  ❌ git-lfs 下载失败 (ghproxy 不可达)"
    echo "     手动安装: https://git-lfs.com/"
    echo "     或 apt-get install git-lfs"
  fi
fi

# 初始化 git-lfs
git lfs install 2>/dev/null || true

# ──────────────────────────────────────────────
# 4. HuggingFace 镜像配置
# ──────────────────────────────────────────────
echo "=== [4/6] HuggingFace 镜像 ==="

if grep -q 'HF_ENDPOINT' ~/.bashrc 2>/dev/null; then
  echo "  ✓ HF_ENDPOINT 已配置"
else
  echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
  echo "  ✓ 已添加 HF_ENDPOINT 到 ~/.bashrc"
fi
export HF_ENDPOINT=https://hf-mirror.com

# ──────────────────────────────────────────────
# 5. git 配置
# ──────────────────────────────────────────────
echo "=== [5/6] git 配置 ==="

{
  echo ".github-token"
  echo ".hf-token"
  echo ".s3cfg"
  echo ".git-credentials-file"
  echo ".git-credential"
} >> .gitignore 2>/dev/null || true

git add .gitignore 2>/dev/null && git commit -m "chore: ignore credential files" --allow-empty 2>/dev/null || true
echo "  ✓ .gitignore 已更新"

# ──────────────────────────────────────────────
# 6. 环境检查
# ──────────────────────────────────────────────
echo "=== [6/6] 环境检查 ==="
ERR=0
check() { python3 -c "$1" 2>/dev/null && echo "  ✓ $2" || { echo "  ✗ $2 FAILED"; ERR=$((ERR+1)); }; }

check "import requests; print(requests.__version__)" "requests"
check "import cv2; print(cv2.__version__)" "opencv"
check "import numpy; print(numpy.__version__)" "numpy"
check "import onnxruntime; print(onnxruntime.__version__)" "onnxruntime"
check "from PIL import Image; print(Image.__version__)" "pillow"

# 检查 git-lfs
if command -v git-lfs &>/dev/null; then
  echo "  ✓ git-lfs ($(git lfs version 2>/dev/null | head -1))"
else
  echo "  ✗ git-lfs 未安装 (LFS 文件将无法拉取)"
  ERR=$((ERR+1))
fi

# 检查 MobileSAM 模型
if [ -f "$SAM_ENCODER" ] && [ -f "$SAM_DECODER" ]; then
  echo "  ✓ MobileSAM 模型 (encoder $(du -h "$SAM_ENCODER" | cut -f1), decoder $(du -h "$SAM_DECODER" | cut -f1))"
else
  echo "  ❌ MobileSAM 模型不完整 (gen_masks.py 无法运行)"
  ERR=$((ERR+1))
fi

# 测试 HF 镜像可达性
python3 -c "
import requests
r = requests.get('https://hf-mirror.com/api/models/depth-anything/Depth-Anything-V2-Large-hf', timeout=10)
if r.status_code in (200, 401, 403):
    print('  ✓ HuggingFace 镜像可达')
else:
    print(f'  ⚠️  HuggingFace 镜像返回 {r.status_code}')
" 2>/dev/null || echo "  ⚠️  HuggingFace 镜像不可达（网络问题？）"

[ $(git log --oneline 2>/dev/null | wc -l) -ge 1 ] && echo "  ✓ git repo" || { echo "  ✗ git repo"; ERR=$((ERR+1)); }

echo ""
if [ $ERR -eq 0 ]; then
  echo "🎉 全部通过，环境就绪！"
  echo ""
  echo "💡 拉取 LFS 大文件 (图片素材): git lfs pull"
  echo ""
  echo "💡 Mask 生成: python3 gen_masks.py"
  echo "   - MobileSAM (ONNX) 精确分割 + Omni 视觉验证"
  echo "   - 首次运行自动下载 MobileSAM 模型 (~2MB)"
  echo ""
  echo "💡 深度估计: python3 gen_depth_lighting.py"
  echo "   - 首次运行自动下载 Depth-Anything-V2-Large (~1.3GB)"
else
  echo "⚠️  ${ERR} 项检查失败，请查看上方输出"
  exit 1
fi
