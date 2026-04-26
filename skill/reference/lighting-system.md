# Lighting System

> WebGL real-time depth-based lighting engine with shadow ray marching.

## Architecture

```
lighting-engine.js    — WebGL lighting engine (standalone module)
lighting-config.json  — Per-scene light source definitions
lighting-editor.html  — Visual editor for development
index.html            — Game (loads engine + config)
```

## Initialization

```javascript
const engine = new LightingEngine(canvas);
await engine.loadScene('apartment', config);
engine.setLights(config.scenes.apartment.lights);
engine.start();
```

## Light Types

| Type | Description | Use Case |
|------|-------------|----------|
| `point` | Position + radius, attenuates with distance | Neon signs, lamps, screens |
| `directional` | Parallel rays, direction vector | Moonlight, car headlights |
| `global` | No direction, uniform | Lightning, ambient pulse |

## Light Parameters

| Param | Description |
|-------|-------------|
| `x, y` | Normalized position (0–1) |
| `color` | RGB array `[r, g, b]` (0–1) |
| `radius` | Point light falloff radius (pixels) |
| `intensity` | Brightness multiplier |
| `depth` | Z-depth plane (0=near, 1=far) |
| `dir` | Direction vector `[dx, dy]` for directional |
| `phase` | Animation phase function (see below) |
| `noise` | Random noise overlay (see below) |

## Phase Animation System

Pre-computed per frame, fed to shader as uniform:

| Type | Formula | Use Case |
|------|---------|----------|
| `steady` | `0.5` (constant) | Ambient baseline |
| `sine` | `0.5 + 0.5 * sin(2π * t * speed + offset)` | Breathing glow |
| `pulse` | Configurable min/max with speed control | Neon signs |
| `flicker` | Irregular random on/off transitions | Broken neon |
| `car_sweep` | Linear position sweep across scene | Car headlights |
| `lightning` | Mostly dark, brief bright flash | Storms |
| `burst` | Rapid irregular intensity bursts | CRT screens |

### Cycle Closure
All frequencies are integer multiples of frame count. With N frames:
- Frame 0 == Frame N (seamless loop)
- `t = frame_idx / num_frames`

## Noise System

Each light can overlay random noise for organic feel:

| Param | Description |
|-------|-------------|
| `noise.intensity` | Noise amplitude (0 = off) |
| `noise.speed` | Noise change rate |
| `noise.phase` | Noise phase offset |

## Shadow Ray March

Per-pixel from surface toward light source, 12 steps:

```glsl
float shadowRayMarch(vec2 pixelUV, vec2 lightUV, float pixelDepth, float lightDepth) {
  vec2 dir = lightUV - pixelUV;
  vec2 stepUV = dir / 12.0;
  float stepDepth = (lightDepth - pixelDepth) / 12.0;

  float shadow = 1.0;
  float blockerThreshold = 0.04;

  for (int s = 1; s <= 12; s++) {
    vec2 sampleUV = pixelUV + stepUV * float(s);
    float sampleDepth = depthAt(sampleUV);

    // Track shallowest surface along ray
    // Deeper pixels behind shallow surface → shadowed
    // Consistently shallowing → not blocked (light passes through)
  }
  return shadow;
}
```

## Depth Attenuation (Geometric Cone Model)

Point lights have XYZ position. Depth-based attenuation:

```javascript
// Pixel in front of light (depth ≤ lightDepth) → full brightness
// Pixel behind light → check elevation angle
elevation = atan(depthDiff * radius, horizontalDist);
coneAngle = 0.4 + 0.3 * clamp(radius / 400, 0, 1);
if (elevation < coneAngle) → lit; else → smoothstep falloff;
// Additional: 1 / (1 + height² × 8) exponential decay
```

## Config File Format

```json
{
  "version": "1.0",
  "canvas": { "width": 960, "height": 640 },
  "ambient": 0.02,
  "scenes": {
    "apartment": {
      "name": "公寓",
      "base": "bg_apartment.png",
      "depth": "apartment_depth.png",
      "lights": [
        {
          "id": "moonlight",
          "name": "月光",
          "type": "directional",
          "x": 0.5, "y": 0.1,
          "color": [0.15, 0.2, 0.4],
          "radius": 0,
          "intensity": 0.8,
          "depth": 0.9,
          "dir": [0.3, -0.7],
          "phase": { "type": "sine", "speed": 1.0 },
          "noise": { "intensity": 0.1, "speed": 0.5, "phase": 0 }
        }
      ]
    }
  }
}
```

## Lighting Editor

Visual editor (`lighting-editor.html`) for real-time parameter tuning:

| Feature | Description |
|---------|-------------|
| Slider controls | Logarithmic curves (gamma 2.2) |
| 3D Gizmo | Drag lights on canvas (R=X, G=Y, B=Z, Shift+drag=Z) |
| Color picker | Sample from rendered canvas |
| Depth overlay | D key to toggle depth visualization |
| Auto depth sampling | Auto-read depth when placing lights |
| Export | Save to `lighting-config.json` |

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `D` | Toggle depth overlay |
| `Shift+drag` | 3D Gizmo Z-axis |
| `Delete` | Remove selected light |

---
**Related workflow chapters:** [03-depth-lighting](../workflow/03-depth-lighting.md) · [05-lighting-engine](../workflow/05-lighting-engine.md) · [05b-lighting-editor](../workflow/05b-lighting-editor.md)
