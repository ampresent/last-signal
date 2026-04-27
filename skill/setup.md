# Environment Setup

## 1. 基础依赖

```bash
pip3 install --break-system-packages \
  requests numpy opencv-python-headless pillow onnxruntime
```

## 2. HuggingFace 镜像（国内必须）

```bash
export HF_ENDPOINT=https://hf-mirror.com
# 写入 ~/.bashrc 持久化
```

## 3. MobileSAM 模型（mask 生成用）

```bash
bash scripts/setup.sh
```

自动下载 encoder + decoder ONNX 模型到 `models/`。

## 4. RMBG-2.0（可选，sprite 抠图对比用）

```bash
pip3 install --break-system-packages transformers torch torchvision
```

首次运行 `rmbg2_cutout.py` 时自动从 HuggingFace 下载模型（~170MB）。

> ⚠️ `torch` 包较大（~2GB），仅在需要对比 RMBG-2 抠图效果时安装。

## 5. 环境验证

```bash
python3 -c "
import requests, cv2, numpy, onnxruntime
from PIL import Image
print('✓ 基础依赖就绪')
try:
    import transformers, torch
    print('✓ RMBG-2 依赖就绪')
except ImportError:
    print('⊘ RMBG-2 未安装（可选）')
"
```

## 一键初始化

```bash
bash scripts/setup.sh
```

处理除 RMBG-2 外的所有依赖。
