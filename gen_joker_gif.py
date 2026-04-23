#!/usr/bin/env python3
"""Generate animated GIF preview of the JOKER face animation."""
import subprocess, os, io
from PIL import Image

FRAMES_DIR = '/tmp/joker_frames'
os.makedirs(FRAMES_DIR, exist_ok=True)

# 6 关键帧 SVG — 直接内联生成
def make_svg(eye_l, eye_r, mouth, brow_l_angle, brow_r_angle, blush=0.15, tears=False):
    """Generate a 160x160 SVG face frame."""
    def eye_svg(cx, cy, w, h, shape):
        if shape == 'square':
            return f'''<rect x="{cx-w/2}" y="{cy-h/2}" width="{w}" height="{h}" fill="#00ff88"/>
            <rect x="{cx-w/4}" y="{cy-h/4}" width="{w/2}" height="{h/2}" fill="#0a0a14"/>
            <rect x="{cx-w/4+2}" y="{cy-h/4}" width="4" height="4" fill="#fff"/>'''
        elif shape == 'circle':
            return f'''<circle cx="{cx}" cy="{cy}" r="{w/2}" fill="#00ff88"/>
            <circle cx="{cx}" cy="{cy}" r="{w/4}" fill="#0a0a14"/>
            <rect x="{cx-2}" y="{cy-w/4}" width="3" height="3" fill="#fff"/>'''
        elif shape == 'line':
            return f'<line x1="{cx-w/2}" y1="{cy}" x2="{cx+w/2}" y2="{cy}" stroke="#00ff88" stroke-width="3"/>'
        return ''

    def mouth_svg(m):
        cx, cy, hw = 80, m['y'], m['w'] * 80
        if m['type'] == 'arc':
            open_h = m['open'] * 25
            pts = []
            for i in range(9):
                t = i / 8
                px = cx - hw + t * hw * 2
                py = cy + __import__('math').sin(t * 3.14159) * open_h
                zigzag = -4 if (i % 2 == 1) else 0
                pts.append(f'{px:.1f},{py + zigzag:.1f}')
            path = f'M{pts[0]} ' + ' '.join(f'L{p}' for p in pts[1:])
            teeth = ''
            if m.get('teeth') and m['open'] > 0.3:
                for i in range(1, 6):
                    tx = cx - hw + (i/6) * hw * 2
                    teeth += f'<rect x="{tx-3}" y="{cy}" width="6" height="{4+i%3*2}" fill="#0a0a14" stroke="#00ff88" stroke-width="0.8"/>'
            return f'<path d="{path}" fill="rgba(0,255,136,0.08)" stroke="#00ff88" stroke-width="2"/>{teeth}'
        elif m['type'] == 'zigzag':
            segs = 10
            open_h = m['open'] * 22
            pts = []
            for i in range(segs + 1):
                t = i / segs
                px = cx - hw + t * hw * 2
                py = cy + (open_h if i % 2 else 0)
                pts.append(f'{px:.1f},{py:.1f}')
            path = f'M{pts[0]} ' + ' '.join(f'L{p}' for p in pts[1:])
            teeth = ''
            if m.get('teeth'):
                for i in range(1, segs, 2):
                    tx = cx - hw + (i/segs) * hw * 2
                    teeth += f'<rect x="{tx-3}" y="{cy}" width="6" height="6" fill="#0a0a14" stroke="#00ff88" stroke-width="0.8"/>'
            return f'<path d="{path}" fill="none" stroke="#00ff88" stroke-width="2"/>{teeth}'
        elif m['type'] == 'circle':
            r = m['w'] * 80
            return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="rgba(0,255,136,0.1)" stroke="#00ff88" stroke-width="2"/>'
        elif m['type'] == 'line':
            return f'<line x1="{cx-hw}" y1="{cy}" x2="{cx+hw}" y2="{cy}" stroke="#00ff88" stroke-width="2"/>'
        return ''

    def brow_svg(cx, cy, angle):
        import math
        x, y = cx * 160, cy * 160
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x1, y1 = x + cos_a * (-10), y + sin_a * (-10)
        x2, y2 = x + cos_a * 10, y + sin_a * 10
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#00ff88" stroke-width="2"/>'

    blush_svg = ''
    if blush > 0.01:
        blush_svg = f'<circle cx="35" cy="88" r="12" fill="rgba(255,0,80,{blush})"/><circle cx="125" cy="88" r="12" fill="rgba(255,0,80,{blush})"/>'

    tears_svg = ''
    if tears:
        tears_svg = '<ellipse cx="45" cy="72" rx="3" ry="4" fill="rgba(0,180,255,0.5)"/><ellipse cx="115" cy="76" rx="2.5" ry="3.5" fill="rgba(0,180,255,0.5)"/>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" width="160" height="160">
  <rect width="160" height="160" fill="#0a0a14"/>
  <g opacity="0.08" stroke="#00ff88" stroke-width="0.5" fill="none">
    {''.join(f'<line x1="{x}" y1="0" x2="{x}" y2="160"/>' for x in range(0, 161, 16))}
    {''.join(f'<line x1="0" y1="{y}" x2="160" y2="{y}"/>' for y in range(0, 161, 16))}
  </g>
  <circle cx="80" cy="80" r="62" fill="rgba(0,255,136,0.03)" stroke="#00ff88" stroke-width="2"/>
  {blush_svg}
  {brow_svg(eye_l[0]-0.02, eye_l[1]-0.10, brow_l_angle)}
  {brow_svg(eye_r[0]+0.02, eye_r[1]-0.10, brow_r_angle)}
  {eye_svg(eye_l[0]*160, eye_l[1]*160, eye_l[2]*160, eye_l[3]*160, eye_l[4])}
  {eye_svg(eye_r[0]*160, eye_r[1]*160, eye_r[2]*160, eye_r[3]*160, eye_r[4])}
  {mouth_svg(mouth)}
  {tears_svg}
  <text x="80" y="150" text-anchor="middle" font-family="monospace" font-size="9" fill="#00ff88" opacity="0.4">SUBJECT_00</text>
</svg>'''

# 6 关键帧定义
FACES = [
    {  # grin
        'eye_l': (0.30, 0.38, 0.14, 0.14, 'square'),
        'eye_r': (0.70, 0.38, 0.14, 0.14, 'square'),
        'mouth': {'type': 'arc', 'open': 0.6, 'w': 0.55, 'y': 108, 'teeth': True},
        'brow_l': -0.1, 'brow_r': 0.1, 'blush': 0.15,
    },
    {  # wink
        'eye_l': (0.30, 0.40, 0.14, 0.03, 'line'),
        'eye_r': (0.70, 0.38, 0.14, 0.14, 'square'),
        'mouth': {'type': 'arc', 'open': 0.4, 'w': 0.45, 'y': 108, 'teeth': False},
        'brow_l': 0.15, 'brow_r': -0.05, 'blush': 0.25,
    },
    {  # evil
        'eye_l': (0.30, 0.36, 0.14, 0.10, 'square'),
        'eye_r': (0.70, 0.36, 0.14, 0.10, 'square'),
        'mouth': {'type': 'zigzag', 'open': 0.8, 'w': 0.60, 'y': 106, 'teeth': True},
        'brow_l': -0.25, 'brow_r': 0.25, 'blush': 0.10,
    },
    {  # surprised
        'eye_l': (0.30, 0.38, 0.16, 0.16, 'circle'),
        'eye_r': (0.70, 0.38, 0.16, 0.16, 'circle'),
        'mouth': {'type': 'circle', 'open': 1.0, 'w': 0.11, 'y': 112, 'teeth': False},
        'brow_l': -0.3, 'brow_r': 0.3, 'blush': 0.05,
    },
    {  # crylaugh
        'eye_l': (0.30, 0.40, 0.10, 0.03, 'line'),
        'eye_r': (0.70, 0.40, 0.10, 0.03, 'line'),
        'mouth': {'type': 'arc', 'open': 0.9, 'w': 0.55, 'y': 106, 'teeth': True},
        'brow_l': 0.2, 'brow_r': -0.2, 'blush': 0.30, 'tears': True,
    },
    {  # blank
        'eye_l': (0.30, 0.38, 0.12, 0.12, 'square'),
        'eye_r': (0.70, 0.38, 0.12, 0.12, 'square'),
        'mouth': {'type': 'line', 'open': 0, 'w': 0.35, 'y': 108, 'teeth': False},
        'brow_l': 0, 'brow_r': 0, 'blush': 0,
    },
]

# 播放序列
SEQUENCE = [0, 1, 0, 2, 3, 0, 4, 5]

# 生成每一帧的 SVG → PNG
def svg_to_png(svg_str, out_path):
    proc = subprocess.run(
        ['rsvg-convert', '-w', '160', '-h', '160', '/dev/stdin', '-o', out_path],
        input=svg_str.encode(), capture_output=True
    )
    return proc.returncode == 0

print("Generating key frames...")
key_pngs = []
for i, face in enumerate(FACES):
    svg = make_svg(face['eye_l'], face['eye_r'], face['mouth'],
                   face['brow_l'], face['brow_r'],
                   face.get('blush', 0), face.get('tears', False))
    path = f'{FRAMES_DIR}/key_{i}.png'
    svg_to_png(svg, path)
    key_pngs.append(Image.open(path))
    print(f"  key frame {i}: {face['mouth']['type']}")

# 生成过渡帧（smoothstep 插值混合）
BLEND_FRAMES = 5  # 两个关键帧之间插值数量
all_frames = []

print("Generating transition frames...")
for seq_idx in range(len(SEQUENCE)):
    img_a = key_pngs[SEQUENCE[seq_idx]]
    img_b = key_pngs[SEQUENCE[(seq_idx + 1) % len(SEQUENCE)]]

    for b in range(BLEND_FRAMES):
        t = b / BLEND_FRAMES
        # smoothstep
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
    duration=80,  # ms per frame
    loop=0,
    optimize=False,
)
print(f"Saved: {GIF_PATH}")
print(f"Size: {os.path.getsize(GIF_PATH)} bytes")
