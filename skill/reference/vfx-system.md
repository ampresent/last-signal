# VFX System

> Canvas-based real-time particle engine. 60fps, zero additional file size.

## Overview

VFX renders on top of AI-generated background frames using Canvas 2D. All effects are procedural — no sprite sheets or pre-rendered assets needed.

## Effect Types

| Effect | Description | Scenes |
|--------|-------------|--------|
| Rain | Angled rain streaks with wind direction | street/alley/rooftop/apartment |
| Rain Splash | Rain hits hard surface (depth detect) → splash particles | Scenes with rain + depth |
| Rain Ripple | Rain hits water (water mask) → concentric rings | Scenes with water surfaces |
| Fog | Radial gradient layers, slow drift | street/rooftop/bar |
| Neon Pulse | Green/purple halo breathing overlay | All scenes |
| Ambient Particles | Dust/steam/smoke/data streams/water drops/wind | Per-scene variety |
| Water Reflection | Scene reflection + wave distortion + specular + ripples | street/alley/tower/rooftop |
| CRT Scanline | Rolling thin lines | apartment/bar/server_room |
| Global Flicker | Random brightness jitter | All except rooftop |
| Glitch | Occasional horizontal displacement + chromatic aberration | All (low probability) |

## Render Order

```
1. Rain (with splash/ripple)
2. Fog
3. Neon pulse
4. Ambient particles
5. Puddle reflection
6. Vignette
7. Flicker
8. Scanlines
9. Glitch
```

## Rain Collision System

### Hard Surface Splash
- Sample depth map: current pixel vs 6px above depth diff > 0.06
- Generate 3–5 splash particles (gravity + fade)

### Water Surface Ripple
- Sample water mask: raindrop lands on white area
- Concentric ring expansion (2–3 rings, 600–900ms duration)

### Priority: Water check first, then hard surface (mutually exclusive)

## Indoor Rain Clipping

```javascript
// Outdoor scenes (street/alley/tower/rooftop): full-screen rain
// Indoor scenes (apartment): rain clipped to window mask

// Implementation:
// 1. Draw rain to temp canvas
// 2. composite: destination-in with mask
// 3. drawImage overlay to main canvas

// Config:
rain: { clipToMask: 'apartment_window' }
// Mask format: {sceneId}_{objId}
```

## Scene Configuration

Per-scene effect combination defined in `VFX.SCENE_CONFIG`:

```javascript
VFX.SCENE_CONFIG = {
  apartment: {
    rain: { intensity: 30, angle: 15, speed: 8, clipToMask: 'apartment_window' },
    scanline: { speed: 0.5, alpha: 0.03 },
    flicker: { intensity: 0.02 },
    ambient: { type: 'dust', count: 15 },
  },
  street: {
    rain: { intensity: 60, angle: 20, speed: 10 },
    rainSplash: true,
    rainRipple: true,
    fog: { layers: 3, speed: 0.2 },
    neon: { colors: ['#ff00ff', '#00ffff'], speed: 0.8 },
    ambient: { type: 'steam', count: 20 },
    puddleReflection: { maskKey: 'street_water', waveSpeed: 0.5 },
    flicker: { intensity: 0.01 },
    vignette: { radius: 0.7, alpha: 0.3 },
  },
  bar: {
    fog: { layers: 2, speed: 0.1 },
    neon: { colors: ['#9900ff', '#ff3300'], speed: 0.6 },
    scanline: { speed: 0.3, alpha: 0.02 },
    ambient: { type: 'smoke', count: 10 },
    flicker: { intensity: 0.015 },
  },
  // ... define per scene
};
```

## Performance Notes

- All particles are simple circles/lines — no sprite drawing
- Particle count kept low (10–60 per effect type)
- Depth map sampling uses pre-loaded ImageData
- Water mask sampling uses pre-loaded ImageData
- No DOM manipulation during render loop

---
**Related workflow chapter:** [04-vfx-engine](../workflow/04-vfx-engine.md)
