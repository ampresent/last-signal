# Gameplay Systems

> Dialogue, inventory, expressions, casual chat, spawn points, and character movement.

## Dialogue System

### Core API
```javascript
// Basic dialogue
await Game.showDialogue("Speaker", "Text content");

// Dialogue with choices
const choice = await Game.showDialogue("Speaker", "Text", [
  { text: "Option 1", action: () => { /* ... */ } },
  { text: "Option 2", action: () => { /* ... */ } },
]);

// With expression (auto-switches portrait)
await Game.showDialogue("Joker", "......", { expression: "angry" });

// Casual chat (non-mainline, repeatable)
await Game.showCasualChat("Speaker", "Text", { expression: "happy" });
```

### Expression System

3 characters × 6 expressions = 18 img2img variants (Pollinations.AI)

| Character | Expressions |
|-----------|-------------|
| Joker | neutral, happy, angry, sad, surprised, thinking |
| Kai | neutral, happy, angry, sad, surprised, thinking |
| Oracle | neutral, happy, angry, sad, surprised, thinking |

Assets: `assets/expressions/{character}_{expression}.png`

### Casual Chat Hotspots

Non-mainline dialogue on interactable objects:

| Scene | Hotspot | Trigger |
|-------|---------|---------|
| Apartment | Radio | Click |
| Street | Ramen stall | Click |
| Bar | Jukebox | Click |
| Alley | Stray cat | Click |
| Tower | Glass shards | Click |

## Inventory System

```javascript
Game.addItem("datachip");     // Add item
Game.removeItem("datachip");  // Remove item
Game.hasItem("datachip");     // Check → boolean
Game.inventory;               // Array of item IDs
```

## Story Flags

```javascript
Game.flags.terminal_hacked = true;
if (Game.flags.terminal_hacked) { /* ... */ }
```

Flags persist within session. Use for branching dialogue and conditional hotspots.

## Sound Effects

```javascript
Game.sfx("click");     // UI click
Game.sfx("pickup");    // Item pickup
Game.sfx("door");      // Door transition
Game.sfx("error");     // Error/failure
Game.sfx("success");   // Success/puzzle solved
```

All sounds are Web Audio API synthesized — no audio files needed.

## Spawn Point System

Character entry position depends on **which scene they came from**:

```javascript
Game.SPAWN_MAP = {
  apartment: {
    rooftop: { x: 0.52, y: 0.57 },  // From rooftop → center
  },
  street: {
    apartment: { x: 0.15, y: 0.70 }, // From apartment → left
    bar:       { x: 0.22, y: 0.65 }, // From bar → bar entrance
    tower:     { x: 0.85, y: 0.70 }, // From tower → right
    alley:     { x: 0.10, y: 0.70 }, // From alley → near alley
  },
  bar: {
    street: { x: 0.85, y: 0.75 },
  },
  // ... etc
};
```

### Usage
```javascript
Game.goScene("street", "apartment");
// Resolves spawn from SPAWN_MAP["street"]["apartment"]
// Falls back to scene default if no mapping
```

## Character Movement

### Click-to-Move
Click walkable area → character auto-pathfinds to target.

### Keyboard
WASD / Arrow keys → 8-directional movement.

### Collision
Real-time check against `walkable_mask.png`:
- White (>128) = walkable
- Black = blocked

### Depth Sorting
Characters sorted by Y coordinate. Lower Y (further away) drawn first.

## Scene Transitions

```javascript
// Edge transitions (defined in SCENES)
{
  id: "to_street",
  label: "出门",
  zone: "bottom",        // Trigger zone: bottom/top/left/right
  size: 50,              // Zone thickness in pixels
  target: "street",      // Target scene ID
}

// Manual transition
Game.goScene("target_scene", "source_scene");
```
