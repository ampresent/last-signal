"""
根据视觉模型识别结果，为每个场景生成交互区域的 mask 文件
白色(255) = 可交互区域，黑色(0) = 背景
支持矩形、椭圆、多边形
"""

from PIL import Image, ImageDraw
import os

W, H = 960, 640
MASK_DIR = "/root/.openclaw/workspace/last-signal/assets/masks"
os.makedirs(MASK_DIR, exist_ok=True)

# 场景名 → 可交互对象列表
# 每个对象: {name, shape, cx_pct, cy_pct, w_pct, h_pct, polygon_points(可选)}
# polygon_points: [[x_pct, y_pct], ...] 百分比坐标

SCENE_MASKS = {
    "apartment": [
        # 终端
        {"name": "terminal", "shape": "rect", "cx_pct": 45, "cy_pct": 45, "w_pct": 22, "h_pct": 25},
        # 窗户
        {"name": "window", "shape": "rect", "cx_pct": 12, "cy_pct": 55, "w_pct": 18, "h_pct": 30},
        # 门
        {"name": "door", "shape": "rect", "cx_pct": 82, "cy_pct": 55, "w_pct": 14, "h_pct": 38},
    ],
    "street": [
        # 酒吧入口（左建筑）
        {"name": "bar", "shape": "rect", "cx_pct": 22, "cy_pct": 48, "w_pct": 28, "h_pct": 45},
        # 右侧街道（通往旧工业带）
        {"name": "road_right", "shape": "rect", "cx_pct": 72, "cy_pct": 42, "w_pct": 26, "h_pct": 50},
        # 小巷入口
        {"name": "alley", "shape": "rect", "cx_pct": 8, "cy_pct": 78, "w_pct": 16, "h_pct": 15},
        # 垃圾桶
        {"name": "dumpster", "shape": "rect", "cx_pct": 50, "cy_pct": 65, "w_pct": 10, "h_pct": 14},
    ],
    "bar": [
        # 酒保（右侧吧台后）
        {"name": "bartender", "shape": "rect", "cx_pct": 62, "cy_pct": 48, "w_pct": 18, "h_pct": 30},
        # 神秘客人/Oracle（角落）
        {"name": "oracle", "shape": "rect", "cx_pct": 28, "cy_pct": 50, "w_pct": 14, "h_pct": 28},
        # 出口（门）
        {"name": "exit", "shape": "rect", "cx_pct": 82, "cy_pct": 50, "w_pct": 14, "h_pct": 38},
    ],
    "alley": [
        # 影子/数据贩子（中间偏右）
        {"name": "shadow", "shape": "rect", "cx_pct": 50, "cy_pct": 48, "w_pct": 22, "h_pct": 35},
        # 涂鸦墙（左侧）
        {"name": "graffiti", "shape": "rect", "cx_pct": 14, "cy_pct": 55, "w_pct": 18, "h_pct": 30},
        # 返回街道（右侧出口）
        {"name": "exit", "shape": "rect", "cx_pct": 88, "cy_pct": 62, "w_pct": 12, "h_pct": 28},
    ],
    "tower": [
        # 正门扫描仪（中心）
        {"name": "scanner", "shape": "rect", "cx_pct": 50, "cy_pct": 50, "w_pct": 18, "h_pct": 35},
        # 警卫亭（左侧）
        {"name": "guard_booth", "shape": "rect", "cx_pct": 18, "cy_pct": 55, "w_pct": 18, "h_pct": 25},
        # 返回街道
        {"name": "exit", "shape": "rect", "cx_pct": 88, "cy_pct": 62, "w_pct": 12, "h_pct": 28},
    ],
    "server": [
        # 终端（中心）
        {"name": "terminal", "shape": "rect", "cx_pct": 50, "cy_pct": 45, "w_pct": 25, "h_pct": 30},
        # 服务器机柜（左侧）
        {"name": "rack", "shape": "rect", "cx_pct": 14, "cy_pct": 50, "w_pct": 14, "h_pct": 50},
        # 通往楼顶的通道（右上）
        {"name": "rooftop_exit", "shape": "rect", "cx_pct": 85, "cy_pct": 40, "w_pct": 12, "h_pct": 38},
        # 返回大厅（左下）
        {"name": "lobby_exit", "shape": "rect", "cx_pct": 8, "cy_pct": 82, "w_pct": 14, "h_pct": 12},
    ],
    "rooftop": [
        # 结局场景无热区
    ],
    "office": [
        # 主显示器/终端
        {"name": "terminal", "shape": "rect", "cx_pct": 37, "cy_pct": 50, "w_pct": 25, "h_pct": 35},
        # 保险柜（右上角服务器柜区域）
        {"name": "safe", "shape": "rect", "cx_pct": 90, "cy_pct": 50, "w_pct": 12, "h_pct": 35},
        # 办公椅
        {"name": "chair", "shape": "polygon", "polygon_points_pct": [
            [73, 60], [70, 85], [79, 86], [82, 60], [78, 58], [75, 58]
        ]},
    ],
}


def draw_shape(draw, obj, w, h):
    """在 mask 上绘制形状"""
    shape = obj["shape"]
    
    if shape == "rect":
        cx = obj["cx_pct"] / 100 * w
        cy = obj["cy_pct"] / 100 * h
        ow = obj["w_pct"] / 100 * w
        oh = obj["h_pct"] / 100 * h
        x0 = cx - ow / 2
        y0 = cy - oh / 2
        x1 = cx + ow / 2
        y1 = cy + oh / 2
        draw.rectangle([x0, y0, x1, y1], fill=255)
        
    elif shape == "ellipse":
        cx = obj["cx_pct"] / 100 * w
        cy = obj["cy_pct"] / 100 * h
        ow = obj["w_pct"] / 100 * w
        oh = obj["h_pct"] / 100 * h
        x0 = cx - ow / 2
        y0 = cy - oh / 2
        x1 = cx + ow / 2
        y1 = cy + oh / 2
        draw.ellipse([x0, y0, x1, y1], fill=255)
        
    elif shape == "polygon":
        points = obj.get("polygon_points_pct") or obj.get("polygon_points")
        if points:
            # 如果是百分比坐标，转换为像素坐标
            abs_points = []
            for pt in points:
                # 检查是否已经是像素坐标（大于100的）
                if pt[0] > 100 or pt[1] > 100:
                    abs_points.append((pt[0], pt[1]))
                else:
                    abs_points.append((pt[0] / 100 * w, pt[1] / 100 * h))
            draw.polygon(abs_points, fill=255)


def generate_masks():
    """为每个场景生成 mask PNG"""
    results = {}
    
    for scene_name, objects in SCENE_MASKS.items():
        mask = Image.new("L", (W, H), 0)  # 灰度图，全黑
        draw = ImageDraw.Draw(mask)
        
        for obj in objects:
            draw_shape(draw, obj, W, H)
        
        filepath = os.path.join(MASK_DIR, f"{scene_name}_mask.png")
        mask.save(filepath)
        
        results[scene_name] = {
            "file": f"assets/masks/{scene_name}_mask.png",
            "objects": [{"name": o["name"], "shape": o["shape"]} for o in objects]
        }
        print(f"✅ {scene_name}_mask.png — {len(objects)} 个交互区域")
    
    return results


if __name__ == "__main__":
    print("=" * 50)
    print("🎭 生成交互区域 Mask")
    print("=" * 50)
    results = generate_masks()
    print(f"\n📁 {MASK_DIR}")
    print(f"共 {sum(len(v['objects']) for v in results.values())} 个交互区域")
