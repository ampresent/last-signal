"""
LAST SIGNAL - 全部游戏图片生成器
使用 Pollinations.AI (免费, 无需API Key)
"""
import urllib.request
import urllib.parse
import os
import time

OUTPUT_DIR = "/root/.openclaw/workspace/last-signal/assets"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE = "https://image.pollinations.ai/prompt/"

STYLE = "pixel art style, 16-bit retro game aesthetic, cyberpunk noir, limited color palette, dark moody atmosphere, rain-soaked, neon accents, detailed pixel art, game background art"

PROMPTS = {
    # === 背景场景 (960x640) ===
    "bg_apartment": f"A small dark cyberpunk apartment room, {STYLE}, messy desk with old computer terminal glowing green, rain on window, dim ceiling light, posters on wall, worn furniture, coffee mug, cables everywhere, top-down slight perspective adventure game view, no characters",
    
    "bg_street": f"A rainy cyberpunk street at night, {STYLE}, wet asphalt reflecting neon signs, tall buildings with glowing windows, street vendor stalls, puddles with reflections, distant flying vehicles, fog, steam from grates, alley entrance visible, adventure game scene",
    
    "bg_bar": f"Interior of a dark cyberpunk bar called The Rust, {STYLE}, counter with bottles, dim neon lighting in purple and red, stools, mysterious patrons in shadows, jukebox, smoke haze, barkeeper behind counter, moody atmosphere, adventure game scene",
    
    "bg_alley": f"A dark narrow cyberpunk back alley, {STYLE}, overflowing dumpsters, graffiti on walls, flickering neon light, puddles, fire escape ladder, cables overhead, trash scattered, shadowy corner, rain dripping, grim atmosphere, adventure game scene",
    
    "bg_tower_exterior": f"Front of a massive corporate tower at night, {STYLE}, imposing dark glass building, rain, security booth, bright lobby lights inside, corporate logo, sleek modern architecture contrasting with dirty street, guards visible, adventure game scene",
    
    "bg_server_room": f"A corporate server room, {STYLE}, rows of server racks with blinking lights in blue and green, cables everywhere, cold fluorescent lighting, terminal screens, humming machines, sterile corporate interior, locked door visible, adventure game scene",
    
    "bg_rooftop": f"A rainy cyberpunk building rooftop at night, {STYLE}, city skyline with neon lights in background, antenna tower, puddles on concrete, wind and rain, helicopter pad markings, edge railing, dramatic atmosphere, fog, adventure game scene",
    
    "bg_office": f"A cyberpunk corporate office, {STYLE}, large desk with holographic display, executive chair, city view through floor-to-ceiling windows, luxury meets decay, filing cabinets, security safe, dim lighting, rain on windows, adventure game scene",
    
    # === 角色肖像 (512x512) ===
    "portrait_kai": f"Character portrait, pixel art, 16-bit retro style, a tired middle-aged male detective in a cyberpunk world, wearing worn leather jacket, short messy hair, stubble, determined tired eyes, cyberpunk noir aesthetic, dark background, upper body portrait, limited color palette, no text",
    
    "portrait_oracle": f"Character portrait, pixel art, 16-bit retro style, a mysterious female hacker informant in a cyberpunk world, wearing hooded jacket, goggles on forehead, short asymmetric hair, neon-colored eyes, confident smirk, cyberpunk noir aesthetic, dark background, upper body portrait, limited color palette, no text",
}

def gen(name, prompt, w, h):
    filepath = os.path.join(OUTPUT_DIR, f"{name}.png")
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        print(f"⏭️  跳过已有: {name}.png")
        return True
    
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE}{encoded}?width={w}&height={h}&seed=2087&model=flux&nologo=true"
    print(f"🎨 生成中: {name}.png ({w}x{h})")
    
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"   ✅ {len(data)//1024}KB → {filepath}")
            return True
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🎮 LAST SIGNAL - 图片生成")
    print("=" * 50)
    
    ok, fail = 0, 0
    for name, prompt in PROMPTS.items():
        if name.startswith("bg_"):
            w, h = 960, 640
        else:
            w, h = 512, 512
        
        if gen(name, prompt, w, h):
            ok += 1
        else:
            fail += 1
        time.sleep(3)
    
    print(f"\n✅ 成功: {ok}  ❌ 失败: {fail}")
    print(f"📁 {OUTPUT_DIR}")
