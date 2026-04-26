#!/usr/bin/env python3
"""
LAST SIGNAL — Asset Build Script
将 PNG 资源压缩为 WebP，大幅减少文件体积，加速游戏加载。

用法:
  python3 build.py              # 完整构建：转换 + 更新引用
  python3 build.py --dry-run    # 仅统计，不修改文件
  python3 build.py --restore    # 恢复 .png 引用（不删除 WebP）

压缩策略:
  - 背景帧 (bg_*): WebP q80, lossy — 体积减少 ~90%
  - Mask: WebP lossless — 二值图无损压缩
  - Sprite: WebP q90, alpha — 透明图保持质量
  - 其他 (depth, portrait, expression): WebP q85
"""

import os
import sys
import io
import glob
import shutil
import json
import argparse
from PIL import Image

# ============================================================
# 配置
# ============================================================

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
INDEX_HTML = os.path.join(ROOT, "index.html")

# 压缩配置
PRESETS = {
    "bg_frames": {
        "pattern": "assets/bg_*_f[0-9]*.png",
        "quality": 80,
        "lossless": False,
        "desc": "背景动画帧",
    },
    "bg_base": {
        "pattern": "assets/bg_*.png",
        "quality": 80,
        "lossless": False,
        "desc": "背景基础图",
        "exclude": "assets/bg_*_f[0-9]*.png",  # 排除帧
    },
    "depth": {
        "pattern": "assets/*_depth.png",
        "quality": 85,
        "lossless": False,
        "desc": "深度图",
    },
    "portraits": {
        "pattern": "assets/portrait_*.png",
        "quality": 85,
        "lossless": False,
        "desc": "角色肖像",
    },
    "expressions": {
        "pattern": "assets/expressions/*.png",
        "quality": 85,
        "lossless": False,
        "desc": "表情变体",
    },
    "sprites": {
        "pattern": "assets/sprites/**/*.png",
        "quality": 90,
        "lossless": False,
        "desc": "角色精灵",
    },
    "masks": {
        "pattern": "assets/masks/*.png",
        "quality": 100,
        "lossless": True,
        "desc": "交互 Mask",
    },
}


# ============================================================
# 转换逻辑
# ============================================================

def convert_png_to_webp(png_path, quality=80, lossless=False):
    """将 PNG 转换为 WebP，返回 (原始大小, 压缩后大小)。"""
    webp_path = png_path.rsplit('.', 1)[0] + '.webp'

    try:
        img = Image.open(png_path)

        # 处理模式
        if img.mode == 'P':
            img = img.convert('RGBA')
        elif img.mode == 'L':
            pass  # 灰度图直接转
        elif img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # 保存 WebP
        save_kwargs = {}
        if lossless:
            save_kwargs['lossless'] = True
            save_kwargs['quality'] = 100
        else:
            save_kwargs['quality'] = quality

        img.save(webp_path, 'WebP', **save_kwargs)

        orig_size = os.path.getsize(png_path)
        webp_size = os.path.getsize(webp_path)
        return orig_size, webp_size

    except Exception as e:
        print(f"  ⚠️  转换失败: {png_path} — {e}")
        return 0, 0


def run_conversion(presets, dry_run=False):
    """执行所有预设的转换，返回统计。"""
    total_orig = 0
    total_webp = 0
    file_count = 0
    stats = {}

    for preset_name, cfg in presets.items():
        pattern = os.path.join(ROOT, cfg["pattern"])
        exclude = cfg.get("exclude")
        files = sorted(glob.glob(pattern, recursive=True))

        if exclude:
            excl_pattern = os.path.join(ROOT, exclude) if not os.path.isabs(exclude) else exclude
            excl_files = set(glob.glob(excl_pattern, recursive=True))
            files = [f for f in files if f not in excl_files]

        if not files:
            continue

        cat_orig = 0
        cat_webp = 0

        for png_path in files:
            if dry_run:
                size = os.path.getsize(png_path)
                cat_orig += size
                file_count += 1
                continue

            orig, webp = convert_png_to_webp(
                png_path,
                quality=cfg["quality"],
                lossless=cfg["lossless"]
            )
            cat_orig += orig
            cat_webp += webp
            file_count += 1

        total_orig += cat_orig
        total_webp += cat_webp

        if cat_orig > 0:
            ratio = (1 - cat_webp / cat_orig) * 100 if not dry_run else 0
            stats[preset_name] = {
                "count": len(files),
                "orig_mb": cat_orig / 1024 / 1024,
                "webp_mb": cat_webp / 1024 / 1024 if not dry_run else 0,
                "ratio": ratio,
            }

    return stats, total_orig, total_webp, file_count


# ============================================================
# 代码引用更新
# ============================================================

def update_references(dry_run=False):
    """将 index.html 中的 .png 引用替换为 .webp（仅限有对应 WebP 文件的）。"""
    if not os.path.exists(INDEX_HTML):
        print("  ❌ index.html 不存在")
        return 0

    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    replacements = 0

    import re

    # 匹配 backtick 模板字面量中的 .png 引用
    # 如: `assets/sprites/${id}_${key}.png`
    # 以及双引号/单引号中的 .png
    png_refs = set()

    # backtick 模板字面量
    for m in re.finditer(r'`([^`]*\.png)`', content):
        png_refs.add(m.group(1))

    # 双引号
    for m in re.finditer(r'"([^"]*\.png)"', content):
        png_refs.add(m.group(1))

    # 单引号
    for m in re.finditer(r"'([^']*\.png)'", content):
        png_refs.add(m.group(1))

    for png_ref in png_refs:
        # 处理模板字面量中的 ${...} 部分
        # 将 .png 替换为 .webp，然后检查是否有对应的静态文件
        webp_ref = png_ref.replace('.png', '.webp')

        # 对于静态路径（无 ${}），直接检查文件是否存在
        if '${' not in png_ref:
            webp_path = os.path.join(ROOT, png_ref)
            if os.path.exists(webp_path.rsplit('.', 1)[0] + '.webp'):
                old_count = content.count(png_ref)
                content = content.replace(png_ref, webp_ref)
                replacements += old_count
        else:
            # 对于动态路径，检查是否有至少一个匹配的 WebP 文件
            # 将 ${...} 替换为 * 来 glob
            import fnmatch
            glob_pattern = re.sub(r'\$\{[^}]+\}', '*', png_ref)
            glob_pattern = os.path.join(ROOT, glob_pattern)
            matching_pngs = glob.glob(glob_pattern)

            if matching_pngs:
                # 检查是否有对应的 webp
                has_webp = any(
                    os.path.exists(p.rsplit('.', 1)[0] + '.webp')
                    for p in matching_pngs
                )
                if has_webp:
                    old_count = content.count(png_ref)
                    content = content.replace(png_ref, webp_ref)
                    replacements += old_count

    if not dry_run and content != original:
        # 备份
        backup_path = INDEX_HTML + '.bak'
        shutil.copy2(INDEX_HTML, backup_path)

        with open(INDEX_HTML, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  💾 已备份: {backup_path}")

    return replacements


def restore_references():
    """恢复 .png 引用。"""
    backup_path = INDEX_HTML + '.bak'
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, INDEX_HTML)
        print(f"  ✅ 已从备份恢复: {backup_path}")
    else:
        print(f"  ❌ 备份不存在: {backup_path}")


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="LAST SIGNAL Asset Builder")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不修改文件")
    parser.add_argument("--restore", action="store_true", help="恢复 .png 引用")
    parser.add_argument("--refs-only", action="store_true", help="仅更新引用（不转换图片）")
    parser.add_argument("--clean", action="store_true", help="删除已转换为 WebP 的原始 PNG 文件")
    args = parser.parse_args()

    print("=" * 60)
    print("📦 LAST SIGNAL — Asset Builder")
    print("=" * 60)

    if args.restore:
        restore_references()
        return

    if not args.refs_only:
        print("\n🖼️  转换 PNG → WebP...\n")
        stats, total_orig, total_webp, file_count = run_conversion(
            PRESETS, dry_run=args.dry_run
        )

        for cat, s in stats.items():
            cfg = PRESETS[cat]
            mode = "lossless" if cfg["lossless"] else f"q{cfg['quality']}"
            print(f"  {cfg['desc']:12s} ({mode:8s}): "
                  f"{s['count']:3d} files, "
                  f"{s['orig_mb']:.1f} MB → {s['webp_mb']:.1f} MB "
                  f"({s['ratio']:.0f}% ↓)")

        total_savings = total_orig - total_webp
        total_ratio = (1 - total_webp / total_orig) * 100 if total_orig > 0 else 0
        print(f"\n  {'总计':12s}: {file_count} files, "
              f"{total_orig/1024/1024:.1f} MB → {total_webp/1024/1024:.1f} MB "
              f"({total_ratio:.0f}% ↓, 节省 {total_savings/1024/1024:.1f} MB)")

    # 更新引用
    print("\n📝 更新代码引用...")
    if args.dry_run:
        refs = update_references(dry_run=True)
        print(f"  [dry-run] 将替换 {refs} 处引用")
    else:
        refs = update_references(dry_run=False)
        print(f"  ✅ 替换了 {refs} 处 .png → .webp 引用")

    if args.dry_run:
        print(f"\n⚠️  以上为 dry-run 结果，未修改任何文件")
    else:
        print(f"\n✅ 构建完成!")
        print(f"📁 WebP 文件已生成在 assets/ 目录")
        print(f"📝 index.html 已更新引用")
        print(f"💾 原始 PNG 文件保留（可选删除以节省空间）")

    # 清理 PNG
    if args.clean and not args.dry_run:
        print(f"\n🗑️  清理已转换的 PNG 文件...")
        removed = 0
        freed = 0
        for webp_path in glob.glob(os.path.join(ASSETS, "**", "*.webp"), recursive=True):
            png_path = webp_path.rsplit('.', 1)[0] + '.png'
            if os.path.exists(png_path):
                size = os.path.getsize(png_path)
                os.remove(png_path)
                freed += size
                removed += 1
        print(f"  ✅ 删除了 {removed} 个 PNG 文件，释放 {freed/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
