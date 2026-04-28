# Pitfalls & Solutions

> Battle-tested solutions from the LAST SIGNAL project. Read before you hit these walls.

## 1. HuggingFace Unreachable in China

**Symptom**: `requests.ConnectionError: Failed to establish a new connection`
**Cause**: DNS resolves huggingface.co to Facebook IP on Alibaba Cloud ECS etc.
**Solution**: Use `hf-mirror.com` (domestic mirror)
```bash
export HF_ENDPOINT=https://hf-mirror.com
```
> ⚠️ hf-mirror.com only serves model downloads, not Serverless Inference API.

## 2. torch `+cpu` Version Breaks transformers

**Symptom**: `TypeError: expected string or bytes-like object, got 'NoneType'`
**Cause**: `importlib.metadata.version('torch')` returns `None` when dist-info dir has `+cpu`
**Solution**: Rename dist-info dir + fix METADATA version string
```bash
mv torch-2.11.0+cpu.dist-info torch-2.11.0.dist-info
sed -i 's/^Version: 2.11.0+cpu/Version: 2.11.0/' torch-2.11.0.dist-info/METADATA
```

## 3. torchvision Stub Incomplete

**Symptom**: `ModuleNotFoundError: No module named 'torchvision.io'`
**Cause**: torchvision stub only implements timm-needed interfaces; transformers 5.x needs more
**Solution**: Manually add `io`, `v2` module stubs + `pil_to_tensor` + `NEAREST_EXACT`

## 4. MobileSAM ONNX Encoder Input Format

**Symptom**: `Invalid rank for input: input_image Got: 4 Expected: 3`
**Cause**: MobileSAM encoder expects `[H, W, 3]` (HWC), not standard `[N, C, H, W]` (NCHW)
**Solution**: Pass `normalized` directly (HWC float32), don't transpose to NCHW

## 5. MobileSAM Needs Two ONNX Files

**Symptom**: `External data path validation failed` or all-black inference
**Cause**: Some HF MobileSAM ONNX models have graph only, weights in `.data` file not uploaded
**Solution**: Use PulpCut/mobilesam-onnx two separate files (all weights embedded):
- `mobilesam.encoder.onnx` (27MB) — image encoder
- `mobile_sam.onnx` (16MB) — mask decoder

## 6. Depth-Anything Direction Inverted

**Symptom**: Characters near = small, far = large (scale direction wrong)
**Cause**: Depth-Anything outputs white=near, black=far. But `getDepth()` returned `pixel/255`, treating white as far (1.0)
**Solution**: Invert in game engine
```javascript
// ✗ Wrong: return this.depthData.data[idx] / 255;
// ✓ Right: return 1.0 - (this.depthData.data[idx] / 255);
```

## 7. s3cmd Requires `--region=auto`

**Symptom**: `InvalidRegionName` error
**Cause**: R2 default region name is not AWS standard
**Solution**: Always add `--region=auto` to all s3cmd commands

## 8. pip `externally-managed-environment`

**Symptom**: Error on Ubuntu 24.04
**Cause**: System Python is externally managed
**Solution**: Add `--break-system-packages` to all pip commands

## 9. HuggingFace Model Mirror for China

**Setup**:
```bash
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
source ~/.bashrc
```

## 10. Green Screen Cutout Quality

**Symptom**: Green fringe on edges, or character parts cut off
**Solution**:
- Use HSV range H=35-85, S≥50, V≥50
- Use GrabCut with HSV as seed
- Process at 128px width, then downscale to 64px
- **Never** erode edges

## 11. Seamless Animation Loop

**Symptom**: Visible "jump" between last and first frame
**Solution**: Use integer-multiple frequencies: `sin(2π * frame/N * k)` where k is integer

## 12. Mask Interaction — No Visual Feedback

**Design rule**: Masks are for detection only. Never draw mask outlines on canvas.

## 13. Omni API Returns Empty Result

**Symptom**: `RuntimeError: Omni 返回空结果`
**Cause**: mimo_api.sh timeout or transient network issue
**Solution**: Built-in retry logic (retry once on failure), wrapped in try-except at caller level

## 14. Iterative Ground Detection — Patches Too Large

**Symptom**: SAM mask includes walls, furniture, non-ground areas
**Cause**: Omni returns large bboxes covering both ground and objects
**Solution**: Use ≤50px small patches + per-patch review (each patch individually judged PASS/FAIL by Omni, FAIL discarded immediately)

## 15. Iterative Ground Detection — Patches Clustered

**Symptom**: All patches at bottom of image (near camera), distant ground missed
**Cause**: Omni defaults to most obvious/prominent ground area
**Solution**: Prompt says "scatter patches at different positions"; next round references existing accepted mask

## 16. MobileSAM v2 Models Not Available on Mirror

**Symptom**: `FileNotFoundError` or 15-byte "Entry not found" files
**Cause**: hf-mirror.com doesn't have PulpCut/mobilesam-onnx v2 models
**Solution**: Use v1 models from R2:
- `deps/mobilesam.encoder.onnx` (27MB)
- `deps/mobile_sam.onnx` (16MB)

---
**Related workflow chapter:** [12-pitfalls](../workflow/12-pitfalls.md)
