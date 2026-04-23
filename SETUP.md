# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置 — 从零到可开发。
>
> **核心原则**：深度模型通过 HuggingFace Serverless Inference API 调用，无需本地部署。

---

## 一键初始化

```bash
cd /root/.openclaw/workspace/last-signal
bash setup.sh
```

自动完成 4 步：阿里云源 → pip 依赖 → HF Token 配置 → 环境检查。

---

## 架构概览

| 组件 | 方式 | 说明 |
|------|------|------|
| 深度估计 | HuggingFace Serverless Inference API | Depth-Anything-V2-Large，远端计算 |
| 图片生成 | Pollinations.AI | 免费文生图/图生图 |
| 帧渲染 | 本地 Python (NumPy + OpenCV) | 光照计算、光流插值 |
| 依赖 | `requests`, `numpy`, `opencv-python-headless` | 无需 torch/torchvision |

---

## 1. 阿里云 pip 源

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

---

## 3. 安装 Python 依赖

```bash
pip3 install --break-system-packages \
  requests numpy opencv-python-headless pillow
```

**无需安装：**
- ~~torch~~ (182MB，已不需要)
- ~~torchvision~~ (ABI 不兼容问题已不存在)
- ~~timm~~ (已不需要)
- ~~transformers~~ (已不需要)
- ~~s3cmd~~ (已不需要)

---

## 4. HuggingFace API Token（可选）

Serverless Inference API 可无 Token 使用，但有速率限制。如需更高配额：

1. 注册 [huggingface.co](https://huggingface.co)（免费）
2. 在 [Settings → Access Tokens](https://huggingface.co/settings/tokens) 创建 Token
3. 存入项目：

```bash
echo 'hf_your_token_here' > .hf-token
chmod 600 .hf-token
```

`.hf-token` 已在 `.gitignore` 中，不会被提交。

---

## 5. 环境检查

```bash
python3 -c "import requests; print(requests.__version__)"
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import numpy; print(numpy.__version__)"
```

---

## 6. 已知问题

### Serverless Inference API 冷启动

首次调用模型时，HuggingFace 可能需要加载模型（~20-60s）。后续调用会很快。
如果遇到 503 错误（模型正在加载），脚本会自动重试。

### 速率限制

无 Token 使用时，API 有较严格的速率限制。建议配置 Token。

---

*最后更新：2026-04-23*
