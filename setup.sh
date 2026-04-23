#!/usr/bin/env bash
# setup.sh — 一键初始化 last-signal 开发环境
# 用法: bash setup.sh [项目目录]
#   默认项目目录: /root/.openclaw/workspace/last-signal
#
# 依赖：requests, opencv-python-headless, numpy
# 深度模型：通过 HuggingFace Serverless Inference API 调用 Depth-Anything-V2-Large
set -euo pipefail

PROJECT="${1:-/root/.openclaw/workspace/last-signal}"
cd "$PROJECT"
echo "📁 项目目录: $(pwd)"

# ──────────────────────────────────────────────
# 0. 阿里云软件源（pip）
# ──────────────────────────────────────────────
echo "=== [0/4] 阿里云软件源 ==="

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
# 1. Python 依赖（轻量，无需 torch）
# ──────────────────────────────────────────────
echo "=== [1/4] Python 依赖 ==="

pip3 install --break-system-packages -q \
  requests numpy opencv-python-headless pillow 2>/dev/null

echo "  ✓ $(python3 -c 'import requests,cv2,numpy; print(f"requests {requests.__version__}, cv2 {cv2.__version__}, numpy {numpy.__version__}")')"

# ──────────────────────────────────────────────
# 2. HuggingFace API Token（可选，提升速率限制）
# ──────────────────────────────────────────────
echo "=== [2/4] HuggingFace API Token ==="

HF_TOKEN_FILE="$PROJECT/.hf-token"
if [ -f "$HF_TOKEN_FILE" ]; then
  echo "  ✓ .hf-token 已存在"
else
  echo "  ⚠️  未找到 .hf-token"
  echo "  💡 Serverless Inference API 可无 Token 使用（有速率限制）"
  echo "     如需更高配额，创建 .hf-token 文件写入你的 HF Token："
  echo "     echo 'hf_xxxx' > $HF_TOKEN_FILE"
fi

# ──────────────────────────────────────────────
# 3. git 配置
# ──────────────────────────────────────────────
echo "=== [3/4] git 配置 ==="

# 凭据文件不入仓库
{
  echo ".github-token"
  echo ".hf-token"
  echo ".s3cfg"
  echo ".git-credentials-file"
} >> .gitignore 2>/dev/null || true

git add .gitignore 2>/dev/null && git commit -m "chore: ignore credential files" --allow-empty 2>/dev/null || true
echo "  ✓ .gitignore 已更新"

# ──────────────────────────────────────────────
# 4. 环境检查
# ──────────────────────────────────────────────
echo "=== [4/4] 环境检查 ==="
ERR=0
check() { python3 -c "$1" 2>/dev/null && echo "  ✓ $2" || { echo "  ✗ $2 FAILED"; ERR=$((ERR+1)); }; }

check "import requests; print(requests.__version__)" "requests"
check "import cv2; print(cv2.__version__)" "opencv"
check "import numpy; print(numpy.__version__)" "numpy"

# 测试 HF API 可达性
python3 -c "
import requests
r = requests.get('https://api-inference.huggingface.co/models/depth-anything/Depth-Anything-V2-Large-hf', timeout=10)
if r.status_code in (200, 401, 403):
    print('  ✓ HuggingFace API 可达')
else:
    print(f'  ⚠️  HuggingFace API 返回 {r.status_code}')
" 2>/dev/null || echo "  ⚠️  HuggingFace API 不可达（网络问题？）"

[ $(git log --oneline 2>/dev/null | wc -l) -ge 1 ] && echo "  ✓ git repo" || { echo "  ✗ git repo"; ERR=$((ERR+1)); }

echo ""
if [ $ERR -eq 0 ]; then
  echo "🎉 全部通过，环境就绪！"
  echo "💡 深度模型通过 HuggingFace Serverless Inference API 调用，无需本地部署"
else
  echo "⚠️  ${ERR} 项检查失败，请查看上方输出"
  exit 1
fi
