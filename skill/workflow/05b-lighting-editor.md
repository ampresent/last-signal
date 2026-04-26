# 光照编辑器

可视化光照参数编辑器（`lighting-editor.html`），用于实时调试光源。

## 功能

| 功能 | 说明 |
|------|------|
| 滑块控件 | 对数曲线（gamma 2.2），适合宽范围参数 |
| 3D Gizmo | 画布上直接拖拽光源位置（红=X, 绿=Y, 蓝=Z, Shift+拖拽=Z） |
| 吸色器 | 从渲染画布采样颜色 |
| 深度地图叠加 | D 键或 🗺️ 按钮切换深度可视化 |
| 自动深度采样 | 📍自动 按钮，点光源放置/拖拽时自动读取深度图 |
| 坐标叠加 | 显示光标位置 + 该点深度值 |
| CORS 安全保存 | 画布导出为 PNG（preserveDrawingBuffer） |
| 随机化 | 一键随机化选中光源参数 |
| 深度/强度范围 | 已扩展到 [0, 1] 全范围 |

## 快捷键

| 键 | 功能 |
|----|------|
| `D` | 切换深度地图叠加 |
| `Shift+拖拽` | 3D Gizmo Z 轴移动 |
| `Delete` | 删除选中光源 |

## 工作流

1. 打开 `lighting-editor.html`
2. 选择场景
3. 点击画布放置光源，或从列表选择现有光源
4. 用滑块调整参数（颜色、强度、半径、相位、噪声）
5. 用 3D Gizmo 直接在画布上拖拽位置
6. 点击 💾 保存到 `lighting-config.json`

---
**Related reference:** [lighting-system](../reference/lighting-system.md)
