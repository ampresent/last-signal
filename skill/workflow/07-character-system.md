# 角色行走系统

## 生成流程（视频→Sprite Sheet）

```
1. AI 平台生成各方向角色行走视频（绿幕背景）
2. ffmpeg 按原始帧率提取帧
3. 多模态模型识别方向 + 选帧
4. HSV 绿幕 + GrabCut 抠图
5. 水平镜像补全缺失方向
6. 裁剪 + 拼合 sprite sheet
```

## 角色数据

3 角色 × 4 方向 × 8 帧 = 96 张行走帧 WebP。

## 移动方式

- **点击移动**：点击可行走区域，自动寻路
- **键盘移动**：WASD / 方向键，8 方向
- **深度排序**：Y 坐标自动排序渲染

## 碰撞检测

使用 `walkable_mask.png`：白色 (>128) = 可行走，黑色 = 不可行走。

## 可行走 Mask 生成

```bash
python3 gen_masks.py              # 所有场景
python3 gen_masks.py --scene bar  # 单个场景
```

## 抠图：绿幕 GrabCut

```python
def green_screen_cutout(img_rgb):
    """HSV 绿幕检测 + GrabCut 精细分割。"""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    green_mask = cv2.inRange(hsv, [35,50,50], [85,255,255])
    # GrabCut: green → GC_BGD, rest → GC_PR_FGD
    # → precise foreground mask
```

**关键**：在 128px 宽度下处理，完成后缩放到 64px。不做边缘腐蚀。

---
**Related references:** [gameplay](../reference/gameplay.md) · [asset-pipeline](../reference/asset-pipeline.md)
