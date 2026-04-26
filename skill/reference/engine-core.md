# Engine Core

> The core game engine: scene management, rendering loop, input handling, and performance patterns.

## Game Object

The central singleton managing all game state:

```javascript
const Game = {
  canvas, ctx,              // Canvas rendering context
  currentScene: null,       // Active scene ID
  bgFrames: {},             // sceneName → [Image, Image, ...] animation frames
  currentFrame: 0,          // Current animation frame index
  frameTimer: 0,            // Animation timer
  frameInterval: 800,       // ms between frame switches
  inventory: [],            // Player inventory items
  flags: {},                // Story state flags (persistent within session)
  masks: null,              // Combined interaction masks
  objMasks: {},             // Per-object masks
  waterMasks: {},           // Water surface masks
  _edgeCache: {},           // Pre-computed mask edge pixels
  _labelCache: {},          // Pre-computed label positions
  _overlayCache: {},        // Pre-computed overlay canvases
};
```

## Scene Definition

Each scene is a JS object:

```javascript
const SCENES = {
  apartment: {
    name: "公寓",
    background: "bg_apartment",        // Asset key (no extension)
    onEnter() {
      // Called when entering scene. Use for intro dialogue.
      if (!Game.flags.visited_apartment) {
        await Game.showDialogue("凯", "这就是 Oracle 说的地方……");
        Game.flags.visited_apartment = true;
      }
    },
    hotspots: [
      {
        x: 500, y: 380, w: 400, h: 247,  // Fallback coordinates
        label: "▸ 检查终端",
        maskId: "apartment_terminal",       // Primary: mask-based detection
        condition: () => !Game.flags.terminal_hacked,
        action() {
          Game.flags.terminal_hacked = true;
          Game.addItem("datachip");
          Game.sfx("success");
        }
      },
      {
        x: 760, y: 140, w: 178, h: 460,
        label: "▸ 出门",
        maskId: "apartment_door",
        action() {
          Game.goScene("street", "apartment");
        }
      }
    ]
  }
};
```

## Scene Transitions

```javascript
// Transition with spawn point resolution
Game.goScene(targetScene, sourceScene);

// Spawn points are resolved from SPAWN_MAP:
Game.SPAWN_MAP = {
  street: {
    apartment: { x: 0.15, y: 0.70 },  // Coming from apartment → left side
    bar:       { x: 0.22, y: 0.65 },  // Coming from bar → bar entrance
  }
};
```

## Rendering Loop

```
loadImages() → loadMasks() → pre-compute edges/labels/overlays
goScene(sceneId) → VFX.init(sceneId) → startRenderLoop()

Each frame (~60fps):
  1. drawImage(bgFrames[currentFrame])     // AI-generated background
  2. VFX.render(ctx, dt, sceneId)          // Particle overlay
  3. drawCharacter()                        // Character sprite
  4. drawHotspotOverlays()                 // Hover highlights (pre-computed)
```

## Performance Patterns

### willReadFrequently
```javascript
const ctx = canvas.getContext('2d', { willReadFrequently: true });
```
Tells browser to use CPU-backed canvas for faster `getImageData()`.

### Pre-computed Mask Data
```javascript
// At load time (expensive):
Game._edgeCache[key] = computeEdgePixels(maskData);     // Array of {x,y}
Game._labelCache[key] = computeLabelCenter(maskData);   // {x,y}
Game._overlayCache[key] = createOverlayCanvas(maskData); // Offscreen canvas

// At render time (cheap):
for (const p of Game._edgeCache[key]) ctx.fillRect(p.x, p.y, 1, 1);
```

### Zero-scan Rendering
Never scan pixels at render time. All mask analysis happens at load time.

## Input Handling

```javascript
// Mouse → scene coordinates
const rect = canvas.getBoundingClientRect();
const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
const my = (e.clientY - rect.top) * (canvas.height / rect.height);

// Mask hit test
Game.isMaskHit(mx, my, maskKey) → boolean

// Keyboard (WASD + arrows for character movement)
document.addEventListener('keydown', (e) => { ... });
```

## Collision Detection

Uses `walkable_mask.png` — white (>128) = walkable, black = blocked:

```javascript
CharSystem.isWalkable(nx, ny) → boolean
// Reads pixel from walkable mask at character position
```

## Depth Sorting

Characters sorted by Y coordinate (depth) for proper occlusion:

```javascript
// Lower Y = further away, drawn first
// Higher Y = closer, drawn last (on top)
characters.sort((a, b) => a.y - b.y);
```

---
**Related workflow chapters:** [11-engine-architecture](../workflow/11-engine-architecture.md) · [01-project-overview](../workflow/01-project-overview.md)
