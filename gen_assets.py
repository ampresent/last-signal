"""
LAST SIGNAL - 游戏图片生成器
使用 Pollinations.AI (免费, 无需API Key)

VFX 引擎版本：不再预渲染多帧，引擎在客户端 Canvas 实时渲染动效。
只需生成每场景 1 张基础背景图 + 角色肖像。

降级方案：如需静态帧序列（无 JS 环境），可运行 gen_anim_frames.py 从基础图扩展。
"""
import urllib.request
import urllib.parse
import os
import time
import sys

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"

STYLE = "pixel art style, 16-bit retro game aesthetic, cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, detailed pixel art, game background art"

NUM_FRAMES = 5

# 每帧的微调修饰词，制造环境动画错觉
# 每帧的 seed 也不同，让 AI 生成略有差异的画面
FRAME_MODS = [
    "",                                                          # f0: 基准
    "slightly brighter neon glow, "                              # f1: 霓虹微亮
    "heavier rain, more reflections on wet surfaces, ",          # f2: 雨变大
    "dimmer ambient light, flickering signs, ",                  # f3: 灯光微暗
    "subtle fog rolling in, softer neon haze, ",                 # f4: 薄雾
]

SCENE_PROMPTS = {
    "bg_apartment": "A small dark cyberpunk apartment room, {style}, messy desk with old computer terminal glowing green, rain on window, dim ceiling light, posters on wall, worn furniture, coffee mug, cables everywhere, top-down slight perspective adventure game view, no characters",

    "bg_street": "A rainy cyberpunk street at night, {style}, wet asphalt reflecting neon signs, tall buildings with glowing windows, street vendor stalls, puddles with reflections, distant flying vehicles, fog, steam from grates, alley entrance visible, adventure game scene",

    "bg_bar": "Interior of a dark cyberpunk bar called The Rust, {style}, counter with bottles, dim neon lighting in purple and red, stools, mysterious patrons in shadows, jukebox, smoke haze, barkeeper behind counter, moody atmosphere, adventure game scene",

    "bg_alley": "A dark narrow cyberpunk back alley, {style}, overflowing dumpsters, graffiti on walls, flickering neon light, puddles, fire escape ladder, cables overhead, trash scattered, shadowy corner, rain dripping, grim atmosphere, adventure game scene",

    "bg_tower_exterior": "Front of a massive corporate tower at night, {style}, imposing dark glass building, rain, security booth, bright lobby lights inside, corporate logo, sleek modern architecture contrasting with dirty street, adventure game scene",

    "bg_server_room": "A corporate server room, {style}, rows of server racks with blinking lights in blue and green, cables everywhere, cold fluorescent lighting, terminal screens, humming machines, sterile corporate interior, locked door visible, adventure game scene",

    "bg_rooftop": "A rainy cyberpunk building rooftop at night, {style}, city skyline with neon lights in background, antenna tower, puddles on concrete, wind and rain, helicopter pad markings, edge railing, dramatic atmosphere, fog, adventure game scene",

    "bg_office": "A cyberpunk corporate office, {style}, large desk with holographic display, executive chair, city view through floor-to-ceiling windows, luxury meets decay, filing cabinets, security safe, dim lighting, rain on windows, adventure game scene",
}

# --- 动画帧生成选项 ---
# VFX 引擎模式（默认）：每场景只生成 1 张基础图，引擎实时渲染动效
# 静态帧模式（--legacy）：每场景生成 5 帧，用于无 JS 环境的降级方案
LEGACY_FRAMES = "--legacy" in sys.argv if 'sys' in dir() else False

PORTRAITS = {
    "portrait_kai": "Character portrait, pixel art, 16-bit retro style, a tired middle-aged male detective in a cyberpunk world, wearing worn leather jacket, short messy hair, stubble, determined tired eyes, cyberpunk noir aesthetic, dark background, upper body portrait, limited color palette, no text",
    "portrait_oracle": "Character portrait, pixel art, 16-bit retro style, a mysterious female hacker informant in a cyberpunk world, wearing hooded jacket, goggles on forehead, short asymmetric hair, neon-colored eyes, confident smirk, cyberpunk noir aesthetic, dark background, upper body portrait, limited color palette, no text",
}


def download(url, filepath):
    """下载图片，返回是否成功"""
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


def gen_scene_base(scene_name, prompt_template):
    """为一个场景生成 1 张基础背景图（VFX 引擎实时渲染动效）"""
    w, h = 960, 640
    base_seed = 2087

    prompt = prompt_template.format(style=STYLE)
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={w}&height={h}&seed={base_seed}&model=flux&nologo=true"

    filename = f"{scene_name}_f0.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    if download(url, filepath):
        return 1
    time.sleep(2)
    return 0


def gen_scene_frames(scene_name, prompt_template):
    """为一个场景生成 5 帧动画（legacy 模式，用于无 JS 环境的降级方案）"""
    w, h = 960, 640
    base_seed = 2087
    ok = 0

    for fi in range(NUM_FRAMES):
        seed = base_seed + fi * 7
        mod = FRAME_MODS[fi]
        prompt = f"{mod}{prompt_template.format(style=STYLE)}"
        encoded = urllib.parse.quote(prompt)
        url = f"{BASE}{encoded}?width={w}&height={h}&seed={seed}&model=flux&nologo=true"

        filename = f"{scene_name}_f{fi}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        if download(url, filepath):
            ok += 1
        time.sleep(2)

    return ok


def gen_portrait(name, prompt):
    """生成角色肖像"""
    w, h = 512, 512
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={w}&height={h}&seed=2087&model=flux&nologo=true"
    filepath = os.path.join(OUTPUT_DIR, f"{name}.png")
    return download(url, filepath)


if __name__ == "__main__":
    use_legacy = "--legacy" in sys.argv

    print("=" * 50)
    print("🎮 LAST SIGNAL - 场景生成")
    if use_legacy:
        print(f"   Legacy 模式: 每场景 {NUM_FRAMES} 帧")
    else:
        print("   VFX 引擎模式: 每场景 1 张基础图 (引擎实时渲染动效)")
    print("=" * 50)

    ok, fail = 0, 0

    # 场景背景
    for scene_name, prompt in SCENE_PROMPTS.items():
        if use_legacy:
            print(f"\n🎬 {scene_name} ({NUM_FRAMES}帧):")
            got = gen_scene_frames(scene_name, prompt)
            ok += got
            fail += (NUM_FRAMES - got)
        else:
            print(f"\n📁 {scene_name}:")
            if gen_scene_base(scene_name, prompt):
                ok += 1
            else:
                fail += 1

    # 角色肖像
    print(f"\n👤 角色肖像:")
    for name, prompt in PORTRAITS.items():
        if gen_portrait(name, prompt):
            ok += 1
        else:
            fail += 1
        time.sleep(2)

    print(f"\n{'='*50}")
    print(f"✅ 成功: {ok}  ❌ 失败: {fail}")
    print(f"📁 {OUTPUT_DIR}")

    # Legacy 模式下也运行动画帧生成
    if use_legacy:
        print(f"\n{'='*50}")
        print("🎬 生成动画帧 (legacy)...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "gen_anim_frames.py")])
    else:
        # Depth Lighting 模式：所有场景使用深度光照渲染
        print(f"\n{'='*50}")
        print("🎬 生成 Depth Lighting 动画帧...")
        import subprocess
        result = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "gen_depth_lighting.py")])
        if result.returncode != 0:
            print("⚠️ Depth Lighting 帧生成失败，可运行 python3 gen_anim_frames.py 作为降级方案")
