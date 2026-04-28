# 踩坑经验

> 实战总结，避免重复踩坑。

## 1. HuggingFace 国内不可达

**现象**：`ConnectionError: Failed to establish a new connection`
**解决**：`export HF_ENDPOINT=https://hf-mirror.com`

## 2. torch `+cpu` 版本号导致 transformers 崩溃

**现象**：`TypeError: expected string or bytes-like object, got 'NoneType'`
**解决**：重命名 dist-info 目录 + 修复 METADATA 版本号

## 3. torchvision stub 不完整

**现象**：`No module named 'torchvision.io'`
**解决**：手动补充 `io`、`v2` 模块 stub

## 4. s3cmd 必须 `--region=auto`

**现象**：`InvalidRegionName`
**解决**：所有 s3cmd 命令加 `--region=auto`

## 5. pip 需要 `--break-system-packages`

**现象**：`externally-managed-environment`
**解决**：所有 pip 命令加 `--break-system-packages`

## 6. MobileSAM ONNX encoder 输入格式是 HWC

**现象**：`Invalid rank for input: Got: 4 Expected: 3`
**解决**：encoder 输入用 `normalized` (HWC float32)，不要 transpose 成 NCHW

## 7. MobileSAM 需要两个 ONNX 文件

**现象**：`External data path validation failed`
**解决**：使用 PulpCut/mobilesam-onnx 的 encoder (27MB) + decoder (16MB)

## 8. Depth-Anything 方向相反

**现象**：角色近处小、远处大
**解决**：`getDepth()` 返回 `1.0 - (pixel/255)` 取反

## 9. 绿幕抠图质量

**规则**：HSV H=35-85, S≥50, V≥50；GrabCut 种子；128px 处理→64px；不腐蚀

## 10. 无缝动画循环

**规则**：相位函数用整数倍频率，保证 frame 0 == frame N

## 11. Omni API 偶尔返回空结果

**现象**：`RuntimeError: Omni 返回空结果`
**原因**：mimo_api.sh 调用超时或网络抖动
**解决**：脚本内置重试逻辑（失败后自动重试一次），外层用 try-except 兜底
**代码**：`gen_ground_mask.py` 的 `omni_analyze_image()` 函数

## 12. Omni 迭代 patch 太大导致误覆盖

**现象**：SAM mask 包含墙壁、家具等非地面区域
**原因**：Omni 返回的 bbox 太大（>200px），覆盖了非地面物体
**解决**：
1. Prompt 明确限制 patch 大小（≤80px）
2. 要求返回 8-15 个小 patch 而不是 3-6 个大 patch
3. 客户端兜底：超过 80px 的 bbox 自动裁剪到中心 80x80
**代码**：`gen_ground_mask.py` 的 `omni_identify_ground_patches()` + `MAX_PATCH_SIZE`

## 13. Omni 迭代 patch 空间分布不均

**现象**：所有 patch 都集中在底部（近景），遗漏远处地面
**原因**：Omni 倾向于选择最明显的地面区域
**解决**：Prompt 中强调"分散在整个地面区域，从近景到远景都要覆盖"

## 14. MobileSAM v2 模型不存在

**现象**：`FileNotFoundError: MobileSAM 模型不存在`
**原因**：hf-mirror.com 上的 v2 模型文件不存在（返回 "Entry not found"）
**解决**：脚本自动 fallback 到 v1 模型（从 R2 下载）
**R2 路径**：`deps/mobilesam.encoder.onnx` (27MB) + `deps/mobile_sam.onnx` (16MB)
**代码**：`gen_ground_mask.py` 的 `MobileSAM.__init__()` 中 `use_v2=True` 自动 fallback

详见 `skill/reference/pitfalls.md` 获取完整解决方案。

---
**Related reference:** [pitfalls](../reference/pitfalls.md)
