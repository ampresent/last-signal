# 对话系统

## 核心 API

```javascript
// 基础对话
await Game.showDialogue("说话者", "文本内容");

// 带选项
const choice = await Game.showDialogue("说话者", "文本", [
  { text: "选项1", action: () => { ... } },
  { text: "选项2", action: () => { ... } },
]);

// 带表情
await Game.showDialogue("Joker", "……", { expression: "angry" });

// 闲聊（非主线，可重复）
await Game.showCasualChat("说话者", "文本", { expression: "happy" });
```

## 表情系统

3 角色 × 6 表情 = 18 张 img2img 表情变体。

| 角色 | 表情 |
|------|------|
| Joker | neutral, happy, angry, sad, surprised, thinking |
| Kai | neutral, happy, angry, sad, surprised, thinking |
| Oracle | neutral, happy, angry, sad, surprised, thinking |

## 闲聊热点

| 场景 | 热点 | 触发方式 |
|------|------|----------|
| 公寓 | 收音机 | 点击 |
| 街道 | 拉面摊 | 点击 |
| 酒吧 | 点唱机 | 点击 |
| 小巷 | 流浪猫 | 点击 |
| 塔楼 | 玻璃碎片 | 点击 |

---
**Related reference:** [gameplay](../reference/gameplay.md)
