#!/usr/bin/env python3
"""Generate JOKER portrait GIF using Pollinations.AI for face frames."""
import subprocess, os, urllib.parse, time
from PIL import Image

OUT_DIR = '/root/.openclaw/workspace/last-signal/assets'
FRAMES_DIR = '/tmp/joker_ai_frames'
os.makedirs(FRAMES_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt"
COMMON = "model=flux&nologo=true&width=512&height=512"

# 6 个表情的提示词 — 保持统一风格，只变表情
PROMPTS = [
    ("grin", "pixel art cyberpunk smiley face, black background, neon green outline, square pixel eyes with small dark pupils, wide zigzag grin mouth showing pixel teeth, glitch aesthetic, minimal, retro 8-bit style, no text"),
    ("wink", "pixel art cyberpunk smiley face, black background, neon green outline, left eye closed as a line, right eye square pixel with pupil, small smirk mouth, playful wink expression, glitch aesthetic, minimal, retro 8-bit style, no text"),
    ("evil", "pixel art cyberpunk smiley face, black background, neon green outline, narrow angry pixel eyes, wide jagged zigzag evil grin mouth with sharp pixel teeth, menacing expression, glitch aesthetic, minimal, retro 8-bit style, no text"),
    ("surprised", "pixel art cyberpunk smiley face, black background, neon green outline, large round pixel eyes with small pupils, round O-shaped mouth open in surprise, shocked expression, glitch aesthetic, minimal, retro 8-bit style, no text"),
    ("crylaugh", "pixel art cyberpunk smiley face, black background, neon green outline, squinting happy eyes as curved lines, wide open laughing mouth with pixel teeth, blue tear drops on cheeks, laughing and crying, glitch aesthetic, minimal, retro 8-bit style, no text"),
    ("blank", "pixel art cyberpunk smiley face, black background, neon green outline, plain square pixel eyes with no emotion, straight line mouth, deadpan expression, emotionless, glitch aesthetic, minimal, retro 8-bit style, no text"),
]

def download(prompt_label, prompt_text, seed=2087):
    path = f'{FRAMES_DIR}/{prompt_label}.png'
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(f"  [cached] {prompt_label}")
        return path
    encoded = urllib.parse.quote(prompt_text)
    url = f"{BASE}/{encoded}?{COMMON}&seed={seed}"
    print(f"  [download] {prompt_label} ...")
    r = subprocess.run(['curl', '-sL', '-o', path, '--max-time', '30', url],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 1000:
        print(f"  [ERROR] {prompt_label} failed!")
        return None
    size = os.path.getsize(path)
    print(f"  [ok] {prompt_label} ({size//1024}KB)")
    return path

# 下载所有帧
print("Downloading frames from Pollinations.AI...")
png_paths = []
for label, prompt in PROMPTS:
    p = download(label, prompt)
    if p:
        png_paths.append((label, p))
    time.sleep(1)  # 礼貌间隔

if len(png_paths) < 2:
    print("ERROR: Not enough frames downloaded!")
    exit(1)

print(f"\nDownloaded {len(png_paths)} frames. Generating GIF...")

# 加载所有图片，统一尺寸
imgs = []
for label, path in png_paths:
    img = Image.open(path).convert('RGBA').resize((512, 512), Image.LANCZOS)
    imgs.append(img)

# 播放序列（循环）
SEQUENCE = list(range(len(imgs)))  # 0,1,2,3,4,5
BLEND_FRAMES = 6  # 每两个关键帧之间的过渡帧数

all_frames = []
for i in range(len(SEQUENCE)):
    img_a = imgs[SEQUENCE[i]].convert('RGB')
    img_b = imgs[SEQUENCE[(i + 1) % len(SEQUENCE)]].convert('RGB')

    for b in range(BLEND_FRAMES):
        t = b / BLEND_FRAMES
        # smoothstep 插值
        s = t * t * (3 - 2 * t)
        blended = Image.blend(img_a, img_b, s)
        all_frames.append(blended)

print(f"Total frames: {len(all_frames)}")

# 保存 GIF
GIF_PATH = '/root/.openclaw/workspace/last-signal/joker_preview.gif'
all_frames[0].save(
    GIF_PATH,
    save_all=True,
    append_images=all_frames[1:],
    duration=100,
    loop=0,
    optimize=False,
)
print(f"Saved: {GIF_PATH} ({os.path.getsize(GIF_PATH)//1024}KB)")
