# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置 — 从零到可开发。
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

## 1. 阿里云 pip 源

```bash
cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
```

---

## 2. Clone 仓库

```bash
git clone https://github.com/ampresent/last-signal.git
```

---

## 3. 安装 Python 依赖

### 3a. PyTorch (从 R2 桶下载，~182MB)

```bash
s3cmd --region=auto get \
  s3://mystore/deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
  /tmp/

pip3 install --break-system-packages \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl

# torchvision stub (5KB, 解决 ABI 不兼容)
s3cmd --region=auto get \
  s3://mystore/deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl \
  /tmp/

pip3 install --break-system-packages --no-deps \
  /tmp/torchvision-0.22.0+cpu.stub-py3-none-any.whl
```

### 3b. 其余依赖

```bash
pip3 install --break-system-packages \
  transformers timm numpy opencv-python-headless requests pillow
```

---

## 4. HuggingFace 镜像配置

国内无法直接访问 huggingface.co，使用镜像下载模型：

```bash
# 设置环境变量（hf-mirror.com 是国内公益镜像）
export HF_ENDPOINT=https://hf-mirror.com

# 或写入 shell profile 持久化
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
```

首次运行 `gen_apartment_lighting.py` 时会自动从镜像下载 Depth-Anything-V2-Large 模型（~1.3GB），
下载后缓存到 `~/.cache/huggingface/`，后续运行跳过。

---

## 5. 环境检查

```bash
python3 -c "import torch; print(torch.__version__)"
python3 -c "import transformers; print(transformers.__version__)"
python3 -c "import timm; print(timm.__version__)"
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import numpy; print(numpy.__version__)"
```

---

## 6. 已知问题

### torch 版本号 `2.11.0+cpu` 导致 transformers 元数据检查失败

`importlib.metadata` 无法正确解析 `+cpu` 后缀。setup.sh 中已包含自动修复。

### HF 镜像首次下载慢

模型 ~1.3GB，首次下载可能需要几分钟。后续运行使用本地缓存。

---

*最后更新：2026-04-23*
