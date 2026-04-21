#!/bin/bash
# 批量识别所有场景的交互对象
SKILL="/root/.openclaw/skills/mimo-omni/mimo_api.sh"
ASSETS="/root/.openclaw/workspace/last-signal/assets"
OUT="/root/.openclaw/workspace/last-signal/mask_data.json"

PROMPT='这是一个像素风赛博朋克point-and-click游戏场景。识别图中所有玩家可以点击/交互的物体（不包括纯装饰背景）。
对每个可交互物体输出：
1) name: 物体名称（中文）
2) cx_pct: 物体中心X位置占图片宽度百分比(0-100)
3) cy_pct: 物体中心Y位置占图片高度百分比(0-100)
4) w_pct: 物体宽度占图片宽度百分比(0-100)
5) h_pct: 物体高度占图片高度百分比(0-100)
6) shape: 形状类型 - rect(矩形), ellipse(椭圆), polygon(不规则多边形)
7) polygon_points: 如果shape是polygon, 输出轮廓顶点坐标数组(百分比), 格式[[x1,y1],[x2,y2],...]; 否则为null

严格按以下JSON格式返回,不要任何其他文字:
[{"name":"xxx","cx_pct":50,"cy_pct":50,"w_pct":20,"h_pct":15,"shape":"rect","polygon_points":null}]'

echo "===== bg_apartment =====" > /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_apartment.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_street =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_street.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_bar =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_bar.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_alley =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_alley.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_tower_exterior =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_tower_exterior.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_server_room =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_server_room.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_rooftop =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_rooftop.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt
echo "" >> /tmp/mask_results.txt

echo "===== bg_office =====" >> /tmp/mask_results.txt
bash "$SKILL" image "$ASSETS/bg_office.png" "$PROMPT" 2>/dev/null >> /tmp/mask_results.txt

echo "✅ All scenes analyzed. Results in /tmp/mask_results.txt"
cat /tmp/mask_results.txt
