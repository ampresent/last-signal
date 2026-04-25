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
echo "=== [0/5] 阿里云软件源 ==="

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
echo "=== [1/5] Python 依赖 ==="

pip3 install --break-system-packages -q \
  requests numpy opencv-python-headless pillow onnxruntime 2>/dev/null

echo "  ✓ $(python3 -c 'import requests,cv2,numpy,onnxruntime; print(f"requests {requests.__version__}, cv2 {cv2.__version__}, numpy {numpy.__version__}, ort {onnxruntime.__version__}")')"

# ──────────────────────────────────────────────
# 2. MobileSAM ONNX 模型
# ──────────────────────────────────────────────
echo "=== [2/5] MobileSAM ONNX 模型 ==="

SAM_MODEL="$PROJECT/models/mobile_sam_vit_t.onnx"
if [ -f "$SAM_MODEL" ]; then
  echo "  ✓ MobileSAM 已存在 ($(du -h "$SAM_MODEL" | cut -f1))"
else
  mkdir -p "$PROJECT/models"
  echo "  ⬇️  下载 MobileSAM..."
  # 优先 hf-mirror.com (国内快)
  if curl -sL "https://hf-mirror.com/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx" \
       -o "$SAM_MODEL" 2>/dev/null && [ -s "$SAM_MODEL" ]; then
    echo "  ✓ 下载完成 ($(du -h "$SAM_MODEL" | cut -f1))"
  else
    echo "  ⚠️  hf-mirror.com 下载失败, 尝试 HuggingFace 原站..."
    curl -sL "https://huggingface.co/gifty-so/mobilesam-onnx/resolve/main/mobile_sam_vit_t.onnx" \
      -o "$SAM_MODEL" 2>/dev/null || true
    if [ -s "$SAM_MODEL" ]; then
      echo "  ✓ 下载完成 ($(du -h "$SAM_MODEL" | cut -f1))"
    else
      rm -f "$SAM_MODEL"
      echo "  ⚠️  MobileSAM 下载失败, gen_masks.py 将使用 GrabCut 降级"
    fi
  fi
fi

# ──────────────────────────────────────────────
# 3. HuggingFace 镜像配置
# ──────────────────────────────────────────────
echo "=== [3/5] HuggingFace 镜像 ==="

if grep -q 'HF_ENDPOINT' ~/.bashrc 2>/dev/null; then
  echo "  ✓ HF_ENDPOINT 已配置"
else
  echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
  echo "  ✓ 已添加 HF_ENDPOINT 到 ~/.bashrc"
fi
export HF_ENDPOINT=https://hf-mirror.com

# ──────────────────────────────────────────────
# 4. git 配置
# ──────────────────────────────────────────────
echo "=== [4/5] git 配置 ==="

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
# 5. 环境检查
# ──────────────────────────────────────────────
echo "=== [5/5] 环境检查 ==="
ERR=0
check() { python3 -c "$1" 2>/dev/null && echo "  ✓ $2" || { echo "  ✗ $2 FAILED"; ERR=$((ERR+1)); }; }

check "import requests; print(requests.__version__)" "requests"
check "import cv2; print(cv2.__version__)" "opencv"
check "import numpy; print(numpy.__version__)" "numpy"
check "import onnxruntime; print(onnxruntime.__version__)" "onnxruntime"
check "from PIL import Image; print(Image.__version__)" "pillow"

# 检查 MobileSAM 模型
if [ -f "$SAM_MODEL" ]; then
  echo "  ✓ MobileSAM 模型 ($(du -h "$SAM_MODEL" | cut -f1))"
else
  echo "  ⚠️  MobileSAM 模型不存在 (将使用 GrabCut 降级)"
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
