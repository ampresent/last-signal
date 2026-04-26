#!/usr/bin/env python3
"""
LAST SIGNAL — 角色缩放比例校准器
使用 Omni 视觉分析场景中物体的高度，结合深度图计算角色在每个场景中的正确缩放比例。

用法:
    python3 calibrate_scales.py              # 分析所有场景
    python3 calibrate_scales.py --scene apartment  # 单个场景
    python3 calibrate_scales.py --apply      # 分析并自动应用到 index.html
"""
import subprocess, os, sys, json, re, argparse

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MIMO_API = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")
GAME_W, GAME_H = 960, 640
CHAR_REAL_HEIGHT = 1.75  # kai 身高 (米)

SCENES = {
    "apartment":   {"bg": "bg_apartment_f0.webp",      "depth": "apartment_depth.webp",    "spawn": [0.52, 0.57]},
    "street":      {"bg": "bg_street_f0.webp",         "depth": "street_depth.webp",       "spawn": [0.48, 0.64]},
    "bar":         {"bg": "bg_bar_f0.webp",            "depth": "bar_depth.webp",          "spawn": [0.51, 0.79]},
    "alley":       {"bg": "bg_alley_f0.webp",          "depth": "alley_depth.webp",        "spawn": [0.57, 0.77]},
    "tower_exterior": {"bg": "bg_tower_exterior_f0.webp", "depth": "tower_exterior_depth.webp", "spawn": [0.51, 0.63]},
    "server_room": {"bg": "bg_server_room_f0.webp",    "depth": "server_room_depth.webp",  "spawn": [0.39, 0.87]},
    "rooftop":     {"bg": "bg_rooftop_f0.webp",        "depth": "rooftop_depth.webp",      "spawn": [0.50, 0.70]},
    "office":      {"bg": "bg_office_f0.webp",         "depth": "office_depth.webp",       "spawn": [0.56, 0.76]},
    "echo_lobby":  {"bg": "bg_echo_lobby_f0.webp",     "depth": "echo_lobby_depth.webp",   "spawn": [0.35, 0.84]},
    "maintenance": {"bg": "bg_maintenance_f0.webp",    "depth": "maintenance_depth.webp",  "spawn": [0.48, 0.81]},
    "data_haven":  {"bg": "bg_data_haven_f0.webp",     "depth": "data_haven_depth.webp",   "spawn": [0.58, 0.78]},
    "flashback":   {"bg": "bg_flashback_f0.webp",      "depth": "flashback_depth.webp",    "spawn": [0.55, 0.76]},
    "hospital":    {"bg": "bg_hospital_f0.webp",        "depth": "hospital_depth.webp",     "spawn": [0.47, 0.79]},
}

PROMPT = """This is a 2D pixel art adventure game scene (960x640 pixels).
A player character (~1.75m tall) stands at the bottom-center of the walkable area.

Identify 2-4 reference objects with known real-world heights (doors ~2m, people ~1.7m, tables ~0.75m, bar counters ~1.1m, windows ~1.2m, server racks ~2m, chairs ~0.45m, trash cans ~0.9m).

For each object, estimate its pixel height in this image.
Also estimate how tall (in pixels) a 1.75m person would appear at the character's standing position.

Reply ONLY with JSON (no markdown, no explanation):
{"objects":[{"name":"door","pixel_height":280,"real_height_m":2.0}],"character_pixel_height_estimate":195}
"""


def call_omni(image_path, prompt):
    """Call mimo-omni to analyze an image."""
    result = subprocess.run(
        ["bash", MIMO_API, "image", image_path, prompt, "--max-tokens", "4096"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Omni call failed: {result.stderr}")
    return result.stdout.strip()


def get_depth_at(depth_path, nx, ny):
    """Get depth value at normalized coordinates. Returns 0-1 (0=near, 1=far)."""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(depth_path).convert("L")
        arr = np.array(img)
        h, w = arr.shape
        px = min(int(nx * w), w - 1)
        py = min(int(ny * h), h - 1)
        return arr[py, px] / 255.0
    except Exception:
        return 0.5  # fallback


def compute_scale(char_pixel_h, depth):
    """Compute the scale value for the character.
    
    char_pixel_h: desired pixel height at spawn position
    depth: depth value at spawn position (0=near, 1=far)
    
    Rendered height = 960 * scale * depthScale
    depthScale = 0.6 + (1.0 - depth) * 0.8
    scale = char_pixel_h / (960 * depthScale)
    """
    depth_scale = 0.6 + (1.0 - depth) * 0.8
    if depth_scale < 0.1:
        depth_scale = 0.1
    scale = char_pixel_h / (GAME_W * depth_scale)
    return round(scale, 3)


def analyze_scene(scene_id, cfg):
    """Analyze one scene and return recommended scale."""
    bg_path = os.path.join(ASSETS, cfg["bg"])
    depth_path = os.path.join(ASSETS, cfg["depth"])

    if not os.path.exists(bg_path):
        print(f"  ❌ Background not found: {bg_path}")
        return None

    print(f"  🔍 Omni analyzing {cfg['bg']}...")
    try:
        response = call_omni(bg_path, PROMPT)
    except Exception as e:
        print(f"  ❌ Omni failed: {e}")
        return None

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{[^{}]*"objects"[^{}]*\[.*?\][^{}]*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
        else:
            # Try finding any JSON object with "objects" key
            json_match = re.search(r'\{.*?"objects".*?\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                print(f"  ❌ No JSON in response: {response[:300]}")
                return None

    # Clean up common JSON issues
    json_str = json_str.strip()
    # Fix trailing commas before } or ]
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON ({e}): {json_str[:300]}")
        return None

    objects = data.get("objects", [])
    char_h_estimate = data.get("character_pixel_height_estimate")

    if not objects:
        print(f"  ❌ No objects found")
        return None

    # Calculate pixels-per-meter from reference objects
    ppm_values = []
    for obj in objects:
        ph = obj.get("pixel_height", 0)
        rh = obj.get("real_height_m", 0)
        if ph > 0 and rh > 0:
            ppm = ph / rh
            ppm_values.append(ppm)
            print(f"    📏 {obj['name']}: {ph}px / {rh}m = {ppm:.0f} px/m")

    if not ppm_values:
        print(f"  ❌ No valid reference objects")
        return None

    # Use median pixels-per-meter
    ppm_values.sort()
    median_ppm = ppm_values[len(ppm_values) // 2]
    print(f"    📐 Median px/m: {median_ppm:.0f}")

    # Calculate character pixel height from reference objects
    char_h_from_refs = median_ppm * CHAR_REAL_HEIGHT
    print(f"    👤 Character height from refs: {char_h_from_refs:.0f}px")

    # Use Omni estimate as secondary reference
    if char_h_estimate:
        print(f"    👤 Omni estimate: {char_h_estimate}px")
        # Average of reference-based and Omni estimate
        char_h = (char_h_from_refs + char_h_estimate) / 2
    else:
        char_h = char_h_from_refs

    # Get depth at spawn position
    spawn = cfg["spawn"]
    depth = get_depth_at(depth_path, spawn[0], spawn[1])
    print(f"    🎯 Spawn ({spawn[0]}, {spawn[1]}): depth = {depth:.3f}")

    # Compute scale
    scale = compute_scale(char_h, depth)
    print(f"    ✅ Recommended scale: {scale}")

    return {
        "scale": scale,
        "char_pixel_h": char_h,
        "depth": depth,
        "ppm": median_ppm,
        "objects": objects,
        "omni_estimate": char_h_estimate,
    }


def apply_to_index_html(results):
    """Apply computed scales to index.html."""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Scene order matches SCENES dict order
    scene_ids = list(SCENES.keys())
    # Map scene_id to its background name for matching
    scene_bg_map = {
        "apartment": "bg_apartment",
        "street": "bg_street",
        "bar": "bg_bar",
        "alley": "bg_alley",
        "tower_exterior": "bg_tower_exterior",
        "server_room": "bg_server_room",
        "rooftop": "bg_rooftop",
        "office": "bg_office",
        "echo_lobby": "bg_echo_lobby",
        "maintenance": "bg_maintenance",
        "data_haven": "bg_data_haven",
        "flashback": "bg_flashback",
        "hospital": "bg_hospital",
    }

    changes = 0
    for scene_id, result in results.items():
        if result is None:
            continue
        new_scale = result["scale"]
        bg_name = scene_bg_map.get(scene_id)
        if not bg_name:
            continue

        # Find the character config for this scene by looking for the background line
        # then finding the next 'scale:' line
        bg_pattern = f"background: '{bg_name}'"
        idx = content.find(bg_pattern)
        if idx == -1:
            print(f"  ⚠️  Could not find {bg_name} in index.html")
            continue

        # Find the next 'scale:' after this background
        scale_idx = content.find("scale:", idx)
        if scale_idx == -1 or scale_idx - idx > 500:
            print(f"  ⚠️  Could not find scale for {scene_id}")
            continue

        # Extract old scale value
        old_match = re.search(r'scale:\s*([\d.]+)', content[scale_idx:scale_idx + 30])
        if old_match:
            old_scale = old_match.group(1)
            # Replace with new scale
            content = content[:scale_idx] + f"scale: {new_scale}" + content[scale_idx + len(f"scale: {old_scale}"):]
            changes += 1
            print(f"  ✏️  {scene_id}: scale {old_scale} → {new_scale}")

    if changes > 0:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n  💾 Updated {changes} scales in index.html")
    else:
        print(f"\n  ℹ️  No changes needed")


def main():
    parser = argparse.ArgumentParser(description="LAST SIGNAL — 角色缩放校准")
    parser.add_argument("--scene", help="分析单个场景")
    parser.add_argument("--apply", action="store_true", help="自动应用到 index.html")
    args = parser.parse_args()

    print("=" * 60)
    print("📏 LAST SIGNAL — 角色缩放比例校准器")
    print(f"   角色身高: {CHAR_REAL_HEIGHT}m")
    print("=" * 60)

    scenes = {args.scene: SCENES[args.scene]} if args.scene else SCENES
    results = {}

    for scene_id, cfg in scenes.items():
        print(f"\n🎬 {scene_id}:")
        result = analyze_scene(scene_id, cfg)
        results[scene_id] = result

    # Summary
    print(f"\n{'=' * 60}")
    print("📊 结果汇总:")
    print(f"{'场景':<18} {'缩放':>6} {'角色px':>8} {'深度':>6} {'px/m':>6}")
    print("-" * 50)
    for scene_id, result in results.items():
        if result:
            print(f"{scene_id:<18} {result['scale']:>6.3f} {result['char_pixel_h']:>7.0f} {result['depth']:>6.3f} {result['ppm']:>6.0f}")
        else:
            print(f"{scene_id:<18} {'N/A':>6}")

    if args.apply:
        print(f"\n📝 应用到 index.html...")
        apply_to_index_html(results)

    print(f"\n{'=' * 60}")
    print("✅ 完成")


if __name__ == "__main__":
    main()
