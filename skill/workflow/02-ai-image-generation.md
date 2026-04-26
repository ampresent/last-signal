# AI 图片生成 (Pollinations.AI)

完全免费，无需注册，无需 API Key，国内可用。

## 文生图 (GET)

```
https://image.pollinations.ai/prompt/{提示词}?width=960&height=640&seed=2087&model=flux&nologo=true
```

## 图生图 (POST)

```bash
curl -X POST \
  "https://image.pollinations.ai/prompt/{提示词}?width=960&height=640&seed=2087&model=flux&nologo=true" \
  -F "image=@base_image.png" \
  -o output.png
```

## 参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `prompt` | 提示词（URL 编码） | 越详细越好 |
| `width/height` | 尺寸 | 960×640（背景）/ 512×512（肖像） |
| `seed` | 随机种子 | `2087`（固定可复现） |
| `model` | 模型 | `flux` |
| `nologo` | 去水印 | `true` |

## 运行

```bash
python3 gen_assets.py          # 基础场景图 + 角色肖像
python3 gen_assets.py --legacy # 基础图 + Legacy 帧（降级）
```

---
**Related reference:** [asset-pipeline](../reference/asset-pipeline.md)
