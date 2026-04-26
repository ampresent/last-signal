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

详见 `skill/reference/pitfalls.md` 获取完整解决方案。

---
**Related reference:** [pitfalls](../reference/pitfalls.md)
