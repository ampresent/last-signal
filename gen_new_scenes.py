#!/usr/bin/env python3
"""Generate new scene base images for LAST SIGNAL via Pollinations.AI"""

import urllib.request
import urllib.parse
import os
import time
import sys

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"
STYLE = "pixel art style, 16-bit retro game aesthetic, cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, detailed pixel art, game background art"

NEW_SCENES = {
    # ── Chapter 1.5: ECHO 塔楼大厅 ──
    "bg_echo_lobby": (
        "Grand corporate lobby of a cyberpunk mega-corp tower, {style}, "
        "marble floor reflecting cold overhead lights, security scanner gates, "
        "holographic corporate logo floating above reception desk, "
        "empty guard post with flickering monitors, "
        "elevator doors with red 'RESTRICTED' signs, "
        "potted plants dying under artificial light, "
        "rain visible through glass doors, "
        "adventure game scene, no characters"
    ),

    # ── Chapter 2: 地下维护通道 ──
    "bg_maintenance": (
        "Narrow underground maintenance tunnel beneath a corporate building, {style}, "
        "exposed pipes and conduits along walls, steam venting from joints, "
        "dim red emergency lighting, puddles on grated floor, "
        "warning signs on walls, rusted metal walls, "
        "distant end of corridor with heavy blast door, "
        "cables hanging from ceiling, dripping water, "
        "industrial decay atmosphere, adventure game scene, no characters"
    ),

    # ── Chapter 2: 数据避难所 (Oracle's hacker den in abandoned subway) ──
    "bg_data_haven": (
        "Abandoned subway station converted into hacker den, {style}, "
        "multiple computer screens glowing in different colors, "
        "cables and wires everywhere like a web, "
        "makeshift workstations on old platform benches, "
        "graffiti on tiled walls, dim neon strips, "
        "old subway train used as living quarters, "
        "food wrappers and energy drink cans, antenna arrays on ceiling, "
        "cyberpunk underground sanctuary, adventure game scene, no characters"
    ),

    # ── Flashback: 三年前的实验室 ──
    "bg_flashback": (
        "Clean sterile corporate laboratory, {style}, "
        "bright white clinical lighting, rows of transparent cylindrical pods with neural interfaces, "
        "scientists in white coats (faded ghostly), "
        "pristine white floor, holographic monitoring displays, "
        "alarm warning lights starting to flash red, "
        "one pod with error warnings on its screen, "
        "everything looks newer and cleaner than present day, "
        "slight desaturated dreamlike quality, adventure game scene, no characters"
    ),

    # ── Epilogue: 医院走廊 ──
    "bg_hospital": (
        "Hospital corridor in a cyberpunk city, {style}, "
        "warm sunlight streaming through large windows at end of hall, "
        "clean white walls with subtle wear, "
        "recovery room doors with patient names on digital displays, "
        "a few people walking in distance (silhouettes), "
        "indoor plants near windows, peaceful atmosphere, "
        "contrast of hope against the usual dark cyberpunk, "
        "morning light breaking through clouds outside, adventure game scene, no characters"
    ),
}

def download(url, filepath):
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        print(f"   ⏭️  已有: {os.path.basename(filepath)}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"   ✅ {os.path.basename(filepath)} ({len(data)//1024}KB)")
            return True
    except Exception as e:
        print(f"   ❌ {os.path.basename(filepath)}: {e}")
        return False

def gen_scene(scene_name, prompt_template):
    w, h = 960, 640
    prompt = prompt_template.format(style=STYLE)
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={w}&height={h}&seed=2087&model=flux&nologo=true"
    filepath = os.path.join(OUTPUT_DIR, f"{scene_name}.png")
    return download(url, filepath)

if __name__ == "__main__":
    scene_filter = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 50)
    print("🎮 LAST SIGNAL — 新场景生成")
    print("=" * 50)

    ok, fail = 0, 0
    for name, prompt in NEW_SCENES.items():
        if scene_filter and name != scene_filter:
            continue
        print(f"\n📁 {name}:")
        if gen_scene(name, prompt):
            ok += 1
        else:
            fail += 1
        time.sleep(3)

    print(f"\n{'='*50}")
    print(f"✅ 成功: {ok}  ❌ 失败: {fail}")
