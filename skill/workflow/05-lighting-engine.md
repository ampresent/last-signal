# 实时光照系统 (WebGL)

基于 WebGL 的逐像素深度光照渲染器，替代预渲染帧序列。

## 架构

```
lighting-engine.js   — WebGL 光照引擎（独立模块）
lighting-config.json  — 各场景光源配置
lighting-editor.html  — 可视化编辑器
index.html            — 游戏主文件
```

## 光源类型

| 类型 | 说明 | 用途 |
|------|------|------|
| `point` | 点光源 | 霓虹灯、台灯、屏幕光 |
| `directional` | 方向光 | 月光、车灯 |
| `global` | 全局光 | 闪电、环境脉冲 |

## 相位动画

| 类型 | 说明 |
|------|------|
| `sine` | 正弦波呼吸 |
| `pulse` | 脉冲（可配速度/min/max） |
| `flicker` | 不规则闪烁 |
| `car_sweep` | 车灯扫过 |
| `lightning` | 闪电 |
| `burst` | 突发闪烁 |
| `steady` | 恒定 |

## 深度遮挡

逐像素阴影射线步进（64 steps）：
- 跟踪路径上最浅表面
- 比最浅表面更深的区域被遮挡
- 持续变浅的区域不遮挡

## 使用

```javascript
const engine = new LightingEngine(canvas);
await engine.loadScene('apartment', config);
engine.setLights(config.scenes.apartment.lights);
engine.start();
```

---
**Related reference:** [lighting-system](../reference/lighting-system.md)
