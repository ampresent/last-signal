#!/usr/bin/env python3
"""Generate expression variants for each character using Pollinations.AI img2img."""
import subprocess, os, urllib.parse, time

BASE_URL = "https://image.pollinations.ai/prompt"
ASSETS = "/root/.openclaw/workspace/last-signal/assets"
OUT_DIR = f"{ASSETS}/expressions"
os.makedirs(OUT_DIR, exist_ok=True)

# 角色 → 基础图
CHARACTERS = {
    "kai": f"{ASSETS}/portrait_kai.png",
    "oracle": f"{ASSETS}/portrait_oracle.png",
    "joker": f"{ASSETS}/portrait_joker.png",
}

# 表情 prompt 模板
EXPRESSIONS = {
    "happy": "same character, happy joyful expression, big smile, bright eyes, cheerful",
    "angry": "same character, angry expression, furrowed brows, clenched teeth, intense eyes",
    "sad": "same character, sad expression, droopy eyes, slight frown, melancholy",
    "surprised": "same character, surprised expression, wide eyes, open mouth, shocked",
    "thinking": "same character, thinking expression, one hand on chin, looking up, contemplative",
    "smirk": "same character, smirking expression, one side of mouth raised, confident, sly grin",
}

def generate_img2img(char_name, base_path, expr_name, prompt_suffix):
    out_path = f"{OUT_DIR}/{char_name}_{expr_name}.png"
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"  [cached] {char_name}/{expr_name}")
        return True

    full_prompt = f"{prompt_suffix}, same art style, same character design, portrait"
    encoded = urllib.parse.quote(full_prompt)
    # Pollinations img2img: POST with image file
    url = f"{BASE_URL}/{encoded}?width=512&height=512&seed=2087&model=flux&nologo=true"

    print(f"  [gen] {char_name}/{expr_name} ...")
    r = subprocess.run(
        ['curl', '-sL', '-o', out_path, '--max-time', '60',
         '-X', 'POST', '-F', f'image=@{base_path}', url],
        capture_output=True, text=True
    )
    if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        print(f"  [FAIL] {char_name}/{expr_name}")
        return False
    print(f"  [ok] {char_name}/{expr_name} ({os.path.getsize(out_path)//1024}KB)")
    return True

# 批量生成
for char_name, base_path in CHARACTERS.items():
    print(f"\n=== {char_name} ===")
    for expr_name, prompt_suffix in EXPRESSIONS.items():
        generate_img2img(char_name, base_path, expr_name, prompt_suffix)
        time.sleep(1)

print("\n✅ Done!")
