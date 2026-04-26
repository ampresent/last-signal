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

Character position is **randomly selected from the walkable mask** each time a scene is entered:

```javascript
// Runtime: random spawn from walkable pixels
Game.getRandomSpawn(sceneId) → [normalizedX, normalizedY]

// Build-time: also samples random spawn into mask_metadata.json (for reference)
// gen_masks.py: _random_walkable_spawn(mask_path)
```

No hardcoded positions. Every entry to a scene picks a random walkable pixel.

See `workflow/15-spawn-system.md` for full documentation.

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

---
**Related workflow chapters:** [06-dialogue-system](../workflow/06-dialogue-system.md) · [07-character-system](../workflow/07-character-system.md) · [15-spawn-system](../workflow/15-spawn-system.md)
