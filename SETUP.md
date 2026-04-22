# 项目初始化指南 (SETUP.md)

> 环境搭建、凭据配置、依赖下载 — 从零到可开发。
>
> **核心原则**：所有大文件（>50MB）优先从 R2 桶下载，避免外网慢速。

---

## 1. Clone 仓库

使用 GitHub Personal Access Token 认证（避免 SSH 配置）：

```bash
# 1. 将 token 存入本地文件（仅当前用户可读）
echo 'YOUR_GITHUB_TOKEN' > /root/.openclaw/workspace/.github-token
chmod 600 /root/.openclaw/workspace/.github-token

# 2. 用 token 文件 clone（保留完整 commit log，禁止浅克隆/压缩包解压）
cd /root/.openclaw/workspace
git clone https://github.com/ampresent/last-signal.git
```

> ⚠️ Token 文件仅用于初始 clone，不要提交到仓库。clone 完成后建议 `git remote set-url origin` 改为 SSH 方式。

---

## 2. 配置 Cloudflare R2 存储桶

项目使用 Cloudflare R2 (`mystore`) 存放模型权重和预缓存依赖。

### 2.1 安装 s3cmd

```bash
pip3 install --break-system-packages s3cmd
```

### 2.2 写入凭据

参考 ./r2mount.py 里的信息，来自动创建 `~/.s3cfg`：

```ini
[default]
access_key = <R2_ACCESS_KEY_ID>
secret_key = <R2_SECRET_ACCESS_KEY>
host_base = <ACCOUNT_ID>.r2.cloudflarestorage.com
host_bucket = %(bucket)s.<ACCOUNT_ID>.r2.cloudflarestorage.com
use_https = True
```

### 2.3 验证连接

```bash
# 列出所有桶（必须加 --region=auto，R2 不接受默认 US 区域名）
s3cmd --region=auto ls
```

预期输出应包含 `s3://mystore`。

### 2.4 常用操作

```bash
s3cmd --region=auto put ./local-file s3://mystore/path/to/file      # 上传
s3cmd --region=auto get s3://mystore/path/to/file ./local-file      # 下载
s3cmd --region=auto ls --recursive s3://mystore/                     # 列出全部
s3cmd --region=auto del s3://mystore/path/to/file                    # 删除
```

> **关键**：所有 `s3cmd` 命令必须带 `--region=auto`，否则会报 `InvalidRegionName: 'US' is not valid`。

---

## 3. 安装 Python 依赖

基础依赖直接 pip 安装（体积小）：

```bash
pip3 install --break-system-packages numpy opencv-python-headless s3cmd
```

### 3.1 PyTorch CPU（~190MB，R2 缓存）

从 PyTorch CDN 直接下载极慢，改从 R2：

```bash
s3cmd --region=auto get \
  s3://mystore/deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl

pip3 install --break-system-packages \
  /tmp/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
```

> 如需其他 Python 版本或平台，替换对应的 wheel 文件名。

### 3.2 transformers + timm

```bash
pip3 install --break-system-packages transformers timm
```

---

## 4. 下载模型文件

### 4.1 Depth-Anything-V2-Large 原始权重（~1.3GB，R2 缓存）

用于 `gen_depth.py` 等脚本直接加载：

```bash
mkdir -p models
s3cmd --region=auto get \
  s3://mystore/depth_anything_v2_vitl.pth \
  models/depth_anything_v2_vitl.pth
```

### 4.2 transformers 格式权重（~1.3GB，R2 缓存）

用于 `gen_apartment_lighting.py` 等通过 transformers 加载的脚本：

```bash
mkdir -p models/depth-anything-v2-large-hf
for f in config.json preprocessor_config.json model.safetensors; do
  s3cmd --region=auto get \
    "s3://mystore/models/depth-anything-v2-large-hf/$f" \
    "models/depth-anything-v2-large-hf/$f"
done
```

然后设置环境变量让 transformers 使用本地文件：

```bash
export HF_ENDPOINT=https://hf-mirror.com   # 回退时使用镜像
# 或者在代码中指定 local_files_only=True + cache_dir
```

> 完整模型也已备份到 R2 以防止 HuggingFace 镜像失效。

---

## 5. R2 桶文件清单

以下大文件已预上传到 `mystore` 桶，初始化时直接下载：

| R2 路径 | 大小 | 用途 |
|---------|------|------|
| `deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` | 182MB | PyTorch CPU wheel |
| `depth_anything_v2_vitl.pth` | 1.3GB | DA2-Large 原始权重 |
| `models/depth-anything-v2-large-hf/model.safetensors` | 1.3GB | DA2-Large transformers 权重 |
| `models/depth-anything-v2-large-hf/config.json` | 1KB | transformers 模型配置 |
| `models/depth-anything-v2-large-hf/preprocessor_config.json` | 1KB | 图像预处理配置 |

---

## 6. 环境检查清单

| 项目 | 检查命令 | 预期结果 |
|------|----------|----------|
| Git 仓库 | `git log --oneline \| wc -l` | 有完整 commit 历史 |
| R2 连接 | `s3cmd --region=auto ls` | 可见 `mystore` 桶 |
| PyTorch | `python3 -c "import torch; print(torch.__version__)"` | 输出版本号 |
| transformers | `python3 -c "import transformers; print(transformers.__version__)"` | 输出版本号 |
| OpenCV | `python3 -c "import cv2; print(cv2.__version__)"` | 输出版本号 |
| DA2 模型 | `ls -lh models/depth_anything_v2_vitl.pth` | ~1.3GB |

---

## 7. FUSE 挂载（可选）

如需将 R2 桶挂载为本地目录（当前环境因 libfuse 版本兼容问题未成功）：

```bash
# rclone（推荐）
rclone config  →  选 s3 → Cloudflare R2
  endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
  region = auto
rclone mount mystore:/ /mnt/mystore --daemon

# goofys（轻量替代）
goofys --region auto --endpoint https://<ACCOUNT_ID>.r2.cloudflarestorage.com mystore /mnt/mystore
```

> 如果只是上传/下载文件，`s3cmd` 已完全够用，无需 FUSE。

---

## 8. 外网依赖安装速度参考

| 包 | 大小 | 来源 | 速度 | 建议 |
|----|------|------|------|------|
| `torch` CPU | ~190MB | PyTorch CDN | 极慢 (20min+) | ✅ 从 R2 下载 |
| `torchvision` CPU | ~7MB | PyTorch CDN | 中等 | pip 直装 |
| `transformers` | ~97MB | PyPI | 快 | pip 直装 |
| `timm` | ~15MB | PyPI | 快 | pip 直装 |
| `opencv-python-headless` | ~40MB | PyPI | 快 | pip 直装 |
| `numpy` | ~42MB | PyPI | 快 | pip 直装 |
| DA2-Large `.pth` | ~1.3GB | HuggingFace/镜像 | 极慢 (3-5min+) | ✅ 从 R2 下载 |
| DA2-Large transformers | ~1.3GB | HuggingFace/镜像 | 极慢 | ✅ 从 R2 下载 |

---

*最后更新：2026-04-22*
