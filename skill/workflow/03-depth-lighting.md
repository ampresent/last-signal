# AI 动画帧生成 — Depth Lighting

## 策略：所有场景统一使用 Depth Lighting

```
bg_{scene}.png (基础图)
       │
       ▼
  hf-mirror.com 下载 Depth-Anything-V2-Large → 本地推理 → {scene}_depth.png
       │
       ▼
  每帧 (f0–f11):
    ├─ 定义 N 个光源参数（位置、颜色、强度、半径、相位函数）
    ├─ 逐像素计算光照
    │   ├─ 距离衰减 (inverse-square)
    │   ├─ 深度调制 (近面更亮)
    │   └─ 阴影光线步进 (64 steps, depth occlusion)
    ├─ 合成: base + lighting (additive blending)
    └─ 保存帧 PNG
```

## 各场景光源配置

| 场景 | 光源 | 效果 |
|------|------|------|
| apartment | 月光、车灯×2、屏幕×2 | 冷蓝月光 + 暖黄方向车灯 + CRT绿光闪烁 |
| street | 霓虹(品红/青)、车灯、积水反射 | 霓虹脉冲 + 车灯扫过 + 地面反射 |
| bar | 紫霓虹、红霓虹、吧台背光、电视 | 紫红呼吸 + 琥珀吧台 + 电视闪烁 |
| alley | 绿霓虹、应急灯、街灯漏光 | 霓虹闪烁 + 红色脉冲 + 远处暖光 |
| tower_exterior | 大厅灯光、玻璃反射、岗亭 | 暖光透出 + 冷色反射 + 恒定岗亭灯 |
| server_room | 蓝LED、绿LED、荧光灯、终端 | LED不规则闪烁 + 荧光灯抖动 + 终端绿光 |
| rooftop | 城市霓虹、闪电、天线灯 | 远处冷色辉光 + 闪电脉冲 + 红色天线灯 |
| office | 全息屏、台灯、窗外城市 | 蓝色全息闪烁 + 暖色台灯 + 冷色窗外 |

## 运行

```bash
export HF_ENDPOINT=https://hf-mirror.com

python3 gen_depth_lighting.py                    # 所有场景
python3 gen_depth_lighting.py --scene apartment   # 单个场景
python3 gen_depth_lighting.py --lighting-only     # 复用已有深度图
python3 gen_depth_lighting.py --depth-only        # 仅深度图
```

## 依赖

`torch`, `transformers`, `timm`, `opencv-python-headless`, `numpy`

## 运行顺序

```bash
export HF_ENDPOINT=https://hf-mirror.com
python3 gen_assets.py              # 1. 基础场景图 + 角色肖像
python3 gen_depth_lighting.py      # 2. Depth Lighting
python3 gen_masks.py               # 3. MobileSAM + Omni mask 生成
```

---
**Related references:** [asset-pipeline](../reference/asset-pipeline.md) · [lighting-system](../reference/lighting-system.md)
