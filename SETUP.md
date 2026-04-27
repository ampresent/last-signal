# SETUP.md — 从零复现指南

前提：只剩 GitHub 仓库 `ampresent/last-signal` 的远程状态是持久的。
所有本地文件（clone、模型、依赖、帧提取）都需要重建。

---

## 第一步：环境准备

```bash
# Clone 仓库
cd /root/.openclaw/workspace
git clone https://github.com/ampresent/last-signal.git
cd last-signal
git checkout feat/rmbg2-cutout

# 设置 git 身份（push 需要）
git config user.name "ampresent"
git config user.email "ampresent@users.noreply.github.com"

# pip 阿里云源
cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
EOF
```

## 第二步：安装 Python 依赖

```bash
# 核心依赖
pip3 install --break-system-packages onnxruntime numpy opencv-python-headless requests pillow boto3

# PyTorch CPU 版（从 R2 下载，国内 PyPI 慢）
pip3 install --break-system-packages boto3
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
os.makedirs('/tmp/r2deps', exist_ok=True)
for key in ['deps/torch-2.11.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl',
 'deps/torchvision-0.22.0+cpu.stub-py3-none-any.whl']:
 fname = os.path.basename(key)
 dest = f'/tmp/r2deps/{fname}'
 if not os.path.exists(dest):
   s3.download_file('mystore', key, dest)
   print(f' {fname} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
pip3 install --break-system-packages --no-cache-dir /tmp/r2deps/torch-*.whl /tmp/r2deps/torchvision-*.whl

# transformers + timm + kornia（清华镜像）
pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple/ --ignore-installed rich transformers timm kornia
```

## 第三步：下载 RMBG-1.4 模型

**方案 A：从 R2 下载（快，推荐）**

```bash
python3 -c "
import boto3, re, os
from pathlib import Path
src = Path('r2mount.py').read_text()
ak = re.search(r'R2_ACCESS_KEY\s*=\s*\"(.+?)\"', src).group(1)
sk = re.search(r'R2_SECRET_KEY\s*=\s*\"(.+?)\"', src).group(1)
ep = re.search(r'R2_ENDPOINT\s*=\s*\"https://(.+?)\"', src).group(1)
s3 = boto3.client('s3', endpoint_url='https://'+ep, aws_access_key_id=ak, aws_secret_access_key=sk, region_name='auto')
os.makedirs('models/RMBG-1.4', exist_ok=True)
for f in ['model.safetensors', 'config.json', 'briarmbg.py', 'MyConfig.py', 'MyPipe.py', 'preprocessor_config.json', 'utilities.py']:
 dest = f'models/RMBG-1.4/{f}'
 if not os.path.exists(dest):
   s3.download_file('mystore', f'deps/RMBG-1.4/{f}', dest)
   print(f' {f} ({os.path.getsize(dest)/1024/1024:.1f} MB)')
"
```

**方案 B：从 HuggingFace 镜像下载（R2 不可用时）**

```bash
HF_ENDPOINT=https://hf-mirror.com python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='briaai/RMBG-1.4',
    local_dir='models/RMBG-1.4',
    ignore_patterns=['*.md', '*.txt', '.gitattributes'],
)
print('Done')
"
```

## 第四步：下载视频并提取帧

```bash
mkdir -p /tmp/sprite-work
curl -L -o /tmp/sprite-work/source.mov \
 "https://cnbj3-fusion.fds.api.xiaomi.com/chatbot-prod/multimedia/1463451899/4fa076a2-dfb1-419a-acff-7ed9d40eb5f2.mov?GalaxyAccessKeyId=AKDFVGPIRVU2J5L22P&Expires=1808833126115&Signature=j+np5arNjZpVB162+l1imxy7nYM="

mkdir -p /tmp/sprite-work/frames
ffmpeg -y -i /tmp/sprite-work/source.mov /tmp/sprite-work/frames/frame_%04d.png
```

## 第五步：裁剪后方向关键帧

```bash
# 角色 kai，视频主体是后（up）方向
# 帧 45-107 是后方向段，均匀选 8 帧关键帧
# 角色中心约 (364, 726)，裁剪区域 x=114-614, y=226-1226（500x1000）
python3 << 'EOF'
from PIL import Image
import os
os.makedirs('/tmp/sprite-work/up_selected', exist_ok=True)
keyframes = [45, 52, 60, 68, 76, 84, 92, 100]
for i, fid in enumerate(keyframes):
 img = Image.open(f'/tmp/sprite-work/frames/frame_{fid:04d}.png')
 cropped = img.crop((114, 226, 614, 1226))
 cropped.save(f'/tmp/sprite-work/up_selected/frame_{i:04d}.png')
 print(f' frame_{i:04d}.png (from frame_{fid:04d}.png)')
EOF
```

## 第六步：跑 RMBG-1.4 抠图

```bash
cd /root/.openclaw/workspace/last-signal

# 单帧模式（逐帧抠图）
python3 skill/scripts/rmbg14_cutout.py up /tmp/sprite-work/up_selected --char kai --no-verify

# Sheet 模式（拼成 4x2 sheet 整张抠，更快）
python3 skill/scripts/rmbg14_cutout.py up /tmp/sprite-work/up_selected --char kai --sheet --no-verify

# 输出到 assets/sprites/kai_up_f{0-7}.webp
```

## 第七步：对比实验（逐帧 vs 拼 sheet）

```bash
# 记录两种模式的耗时对比
# 单帧：每帧独立推理
# Sheet：8帧拼成4x2大图，推理1次，再拆帧
```

## 第八步：更新 Skill 并 Push

```bash
git add -A && git commit -m "feat: switch to RMBG-1.4" && git push
```

---

## RMBG-1.4 vs RMBG-2.0 差异说明

| 项目 | RMBG-1.4 | RMBG-2.0 |
|------|----------|----------|
| 模型大小 | ~169MB (safetensors) | ~176MB |
| HF Token | 不需要（公开模型） | 需要 |
| 自定义代码 | briarmbg.py + utilities.py | 自带 |
| 预处理 | normalize([0.5,0.5,0.5], [1.0,1.0,1.0]) | ImageNet stats |
| 后处理 | min-max 归一化 → 0-255 | sigmoid > 0.5 阈值 |
| R2 路径 | `deps/RMBG-1.4/` | `deps/RMBG-2.0/` |
