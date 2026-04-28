#!/usr/bin/env python3
"""
Generate PDF report for iterative ground detection process.
Records all intermediate states and thinking process in English.
"""

import json
import os
import re
from datetime import datetime
from fpdf import FPDF
from pathlib import Path


def sanitize(text):
    """Remove non-latin1 characters (Chinese etc.) for PDF compatibility."""
    if not isinstance(text, str):
        return str(text)
    # Replace common Chinese labels with English equivalents
    replacements = {
        "地面": "ground", "地板": "floor", "路面": "road surface",
        "巷子": "alley", "小巷": "alley", "积水": "puddle",
        "墙壁": "wall", "家具": "furniture", "桌子": "table",
        "柜子": "cabinet", "垃圾桶": "trash bin", "设备": "equipment",
        "终端": "terminal", "窗户": "window", "门": "door",
        "涂鸦": "graffiti", "影子": "shadow", "过道": "aisle",
        "文件柜": "file cabinet", "桌腿": "table legs",
        "反光": "reflective", "湿漉漉": "wet", "人行道": "sidewalk",
        "卷帘门": "roller shutter", "门口": "doorway",
        "误覆盖": "overcover", "遗漏": "missing",
        "红色金属架": "red metal rack", "黑色垃圾桶": "black trash bin",
        "深处": "deep area", "中央": "center", "前方": "front",
        "左侧": "left side", "右侧": "right side",
        "前轮": "previous round", "已识别": "already identified",
        "请识别": "please identify", "尚未覆盖": "not yet covered",
        "重点关注": "focus on", "地板材质连续": "continuous floor material",
        "人行道、路面": "sidewalk, road", "地板、台阶": "floor, stairs",
        "可行走表面": "walkable surface", "墙壁、窗户": "wall, window",
        "家具、人物、杂物": "furniture, people, clutter",
    }
    for cn, en in replacements.items():
        text = text.replace(cn, en)
    # Remove remaining non-latin1 chars
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text

LOG_DIR = "/root/.openclaw/workspace/last-signal/ground_detection_logs"
OUTPUT_PDF = "/root/.openclaw/workspace/last-signal/ground_detection_report.pdf"


class GroundDetectionReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "LAST SIGNAL - Iterative Ground Detection Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title, level=1):
        sizes = {1: 16, 2: 13, 3: 11}
        self.set_font("Helvetica", "B", sizes.get(level, 11))
        self.set_text_color(30, 30, 30)
        self.ln(4)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        if level == 1:
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(2)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 5, sanitize(text))
        self.ln(1)

    def kv_pair(self, key, value):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(60, 60, 60)
        x = self.get_x()
        self.cell(45, 5, key + ":")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 30)
        self.cell(0, 5, sanitize(str(value)), new_x="LMARGIN", new_y="NEXT")

    def add_image_if_exists(self, path, w=80, caption=""):
        if os.path.exists(path) and os.path.getsize(path) > 100:
            try:
                self.image(path, w=w)
                if caption:
                    self.set_font("Helvetica", "I", 7)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 4, caption, align="C", new_x="LMARGIN", new_y="NEXT")
                self.ln(2)
                return True
            except Exception:
                pass
        return False

    def divider(self):
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)


def build_report():
    pdf = GroundDetectionReport()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Cover Page ──
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 15, "Iterative Ground Detection", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "LAST SIGNAL - Walkable Mask Generation", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Omni Vision + MobileSAM Pipeline", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Scenes: Apartment & Alley", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Branch: feat/rmbg2-cutout", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Table of Contents ──
    pdf.add_page()
    pdf.section_title("Table of Contents")
    toc = [
        "1. Methodology Overview",
        "2. Pipeline Architecture",
        "3. Scene: Apartment - Round-by-Round Analysis",
        "4. Scene: Alley - Round-by-Round Analysis",
        "5. Summary & Results",
        "6. Appendix: Raw Data"
    ]
    for item in toc:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, item, new_x="LMARGIN", new_y="NEXT")

    # ── Section 1: Methodology ──
    pdf.add_page()
    pdf.section_title("1. Methodology Overview")
    pdf.body_text(
        "This report documents the iterative ground detection pipeline used to generate "
        "walkable area masks for the LAST SIGNAL cyberpunk point-and-click adventure game. "
        "The goal is to accurately identify ground/floor surfaces in scene backgrounds, "
        "which are used for character navigation and collision detection.\n\n"
        "The pipeline uses a two-model approach:\n"
        "- Omni Vision Model (MiMo/clawm-alpha): Identifies ground patches as bounding boxes "
        "and reviews overlay results\n"
        "- MobileSAM v1 (ONNX): Generates precise segmentation masks from bounding box prompts\n\n"
        "The iterative process works as follows:\n"
        "1. Omni identifies 3-6 small ground patches (bounding boxes)\n"
        "2. SAM generates a binary mask for each patch\n"
        "3. Masks are composited onto a cumulative ground mask\n"
        "4. Omni reviews the overlay (green = ground) and provides PASS/FAIL verdict\n"
        "5. If FAIL, Omni suggests MISSING (uncovered) and OVERCOVER (false positive) regions\n"
        "6. Process repeats for up to 3 rounds\n\n"
        "Key Design Decisions:\n"
        "- Small patches: Each Omni call returns small boxes for precise SAM segmentation\n"
        "- Incremental overlay: Each round adds to the cumulative mask (OR operation)\n"
        "- Morphological cleanup: CLOSE + OPEN operations smooth mask edges\n"
        "- Overcover removal: False positives are subtracted from the cumulative mask"
    )

    # ── Section 2: Pipeline Architecture ──
    pdf.add_page()
    pdf.section_title("2. Pipeline Architecture")
    pdf.body_text(
        "The pipeline consists of the following stages:\n\n"
        "Stage 1 - Omni Ground Patch Identification\n"
        "  Input: Scene background image (940x627 px)\n"
        "  Output: JSON array of bounding boxes [{id, label, bbox}]\n"
        "  Prompt: 'Identify 3-6 small ground/floor patches'\n\n"
        "Stage 2 - MobileSAM Segmentation\n"
        "  Input: Scene image + bounding box\n"
        "  Output: Binary mask (940x627, 0/255)\n"
        "  Method: Encoder extracts embeddings, decoder generates mask from bbox prompt\n\n"
        "Stage 3 - Mask Composition\n"
        "  Operation: cumulative_mask = OR(composite_mask, new_mask)\n"
        "  Cleanup: Morphological CLOSE (fill gaps) + OPEN (remove noise)\n\n"
        "Stage 4 - Omni Review\n"
        "  Input: Scene image with green overlay on detected ground\n"
        "  Output: PASS/FAIL + MISSING/OVERCOVER suggestions\n"
        "  Criteria: Coverage accuracy, no false positives, no major gaps\n\n"
        "Stage 5 - Iteration Control\n"
        "  Max rounds: 3\n"
        "  Termination: PASS from Omni, or max rounds reached\n"
        "  Post-processing: Subtract object masks, final morphological cleanup"
    )

    # ── Section 3: Apartment ──
    pdf.add_page()
    pdf.section_title("3. Scene: Apartment - Round-by-Round Analysis")

    # Load apartment log
    apt_log_path = os.path.join(LOG_DIR, "apartment_log_20260428_165523.json")
    with open(apt_log_path) as f:
        apt = json.load(f)

    pdf.kv_pair("Scene", "apartment")
    pdf.kv_pair("Image", "bg_apartment.webp (940x627)")
    pdf.kv_pair("Total Rounds", str(apt["final_result"]["total_rounds"]))
    pdf.kv_pair("Final Coverage", f'{apt["final_result"]["coverage_pct"]:.1f}%')
    pdf.kv_pair("Total Time", apt["final_result"]["total_time"])
    pdf.ln(3)

    # Scene image
    pdf.body_text("Original scene background:")
    pdf.add_image_if_exists(
        "/root/.openclaw/workspace/last-signal/assets/bg_apartment.webp",
        w=90, caption="Figure: Apartment scene background"
    )

    for rd in apt["rounds"]:
        rn = rd["round"]
        pdf.add_page()
        pdf.section_title(f"  Round {rn}", level=2)

        # Omni proposals
        pdf.section_title("    Step 1: Omni Ground Patch Identification", level=3)
        proposals = rd["omni_proposals"]
        if proposals:
            boxes = proposals[0]["boxes"]
            pdf.body_text(f"Omni identified {len(boxes)} ground patches:")
            for box in boxes:
                bbox = box["bbox"]
                pdf.body_text(
                    f'  - {box["id"]}: "{box["label"]}" '
                    f'at [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]'
                )

        # SAM results
        pdf.section_title("    Step 2: MobileSAM Segmentation", level=3)
        pdf.body_text("SAM generated masks for each patch:")
        for sam in rd["sam_results"]:
            pdf.body_text(
                f'  - {sam["box_id"]}: bbox {sam["bbox"]} -> '
                f'{sam["area_pct"]:.1f}% coverage'
            )

        # Show individual patch masks in a row
        pdf.body_text("Individual patch masks:")
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        img_w = 35
        count = 0
        for sam in rd["sam_results"]:
            mask_path = sam["mask_path"]
            if os.path.exists(mask_path) and os.path.getsize(mask_path) > 100:
                try:
                    pdf.image(mask_path, x=x_start + count * (img_w + 2), y=y_start, w=img_w)
                    count += 1
                except Exception:
                    pass
        if count > 0:
            pdf.set_y(y_start + img_w * 0.67 + 5)
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 4, f"Figure: Individual patch masks (Round {rn})", align="C", new_x="LMARGIN", new_y="NEXT")

        # Composition
        pdf.section_title("    Step 3: Mask Composition", level=3)
        overlay_steps = [s for s in rd["steps"] if s["type"] == "overlay"]
        if overlay_steps:
            pdf.body_text(f'Cumulative ground coverage: {overlay_steps[0]["content"]}')

        # Show ground mask
        ground_path = os.path.join(LOG_DIR, f"apartment_round{rn}_ground.png")
        pdf.add_image_if_exists(ground_path, w=80,
                                caption=f"Figure: Cumulative ground mask after Round {rn}")

        # Show preview overlay
        preview_path = os.path.join(LOG_DIR, f"apartment_round{rn}_preview.png")
        pdf.add_image_if_exists(preview_path, w=80,
                                caption=f"Figure: Ground overlay preview (Round {rn})")

        # Omni review
        pdf.section_title("    Step 4: Omni Review", level=3)
        reviews = rd["overlay_reviews"]
        if reviews:
            rev = reviews[0]
            status = "PASS" if rev["passed"] else "FAIL"
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 128, 0) if rev["passed"] else pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 6, f"Verdict: {status}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(50, 50, 50)

            # Parse review for MISSING/OVERCOVER
            review_text = rev["review"]
            if "MISSING" in review_text or "OVERCOVER" in review_text:
                pdf.body_text("Corrections suggested:")
                for line in review_text.split("\n"):
                    line = line.strip()
                    if line.startswith("MISSING") or line.startswith("OVERCOVER"):
                        pdf.body_text(f"  {line}")

            if not rev["passed"]:
                pdf.body_text(f"Full review: {review_text[:300]}...")

    # Final result for apartment
    pdf.add_page()
    pdf.section_title("  Apartment - Final Result", level=2)
    pdf.body_text(f"Final walkable mask: apartment_walkable_mask.png")
    pdf.body_text(f"Coverage: {apt['final_result']['coverage_pct']:.1f}%")
    pdf.body_text(f"Rounds: {apt['final_result']['total_rounds']}")

    final_preview = os.path.join(LOG_DIR, "apartment_final_preview.png")
    pdf.add_image_if_exists(final_preview, w=90,
                            caption="Figure: Final apartment ground mask overlay")

    # ── Section 4: Alley ──
    pdf.add_page()
    pdf.section_title("4. Scene: Alley - Round-by-Round Analysis")

    alley_log_path = os.path.join(LOG_DIR, "alley_log_20260428_165915.json")
    with open(alley_log_path) as f:
        alley = json.load(f)

    pdf.kv_pair("Scene", "alley")
    pdf.kv_pair("Image", "bg_alley.webp (940x627)")
    pdf.kv_pair("Total Rounds", str(alley["final_result"]["total_rounds"]))
    pdf.kv_pair("Final Coverage", f'{alley["final_result"]["coverage_pct"]:.1f}%')
    pdf.kv_pair("Total Time", alley["final_result"]["total_time"])
    pdf.ln(3)

    # Scene image
    pdf.body_text("Original scene background:")
    pdf.add_image_if_exists(
        "/root/.openclaw/workspace/last-signal/assets/bg_alley.webp",
        w=90, caption="Figure: Alley scene background"
    )

    for rd in alley["rounds"]:
        rn = rd["round"]
        pdf.add_page()
        pdf.section_title(f"  Round {rn}", level=2)

        # Omni proposals
        pdf.section_title("    Step 1: Omni Ground Patch Identification", level=3)
        proposals = rd["omni_proposals"]
        if proposals:
            boxes = proposals[0]["boxes"]
            pdf.body_text(f"Omni identified {len(boxes)} ground patches:")
            for box in boxes:
                bbox = box["bbox"]
                pdf.body_text(
                    f'  - {box["id"]}: "{box["label"]}" '
                    f'at [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]'
                )

        # SAM results
        pdf.section_title("    Step 2: MobileSAM Segmentation", level=3)
        for sam in rd["sam_results"]:
            pdf.body_text(
                f'  - {sam["box_id"]}: bbox {sam["bbox"]} -> '
                f'{sam["area_pct"]:.1f}% coverage'
            )

        # Show individual patch masks
        pdf.body_text("Individual patch masks:")
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        img_w = 35
        count = 0
        for sam in rd["sam_results"]:
            mask_path = sam["mask_path"]
            if os.path.exists(mask_path) and os.path.getsize(mask_path) > 100:
                try:
                    pdf.image(mask_path, x=x_start + count * (img_w + 2), y=y_start, w=img_w)
                    count += 1
                except Exception:
                    pass
        if count > 0:
            pdf.set_y(y_start + img_w * 0.67 + 5)
            pdf.set_font("Helvetica", "I", 7)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 4, f"Figure: Individual patch masks (Round {rn})", align="C", new_x="LMARGIN", new_y="NEXT")

        # Composition
        pdf.section_title("    Step 3: Mask Composition", level=3)
        overlay_steps = [s for s in rd["steps"] if s["type"] == "overlay"]
        if overlay_steps:
            pdf.body_text(f'Cumulative ground coverage: {overlay_steps[0]["content"]}')

        ground_path = os.path.join(LOG_DIR, f"alley_round{rn}_ground.png")
        pdf.add_image_if_exists(ground_path, w=80,
                                caption=f"Figure: Cumulative ground mask after Round {rn}")

        preview_path = os.path.join(LOG_DIR, f"alley_round{rn}_preview.png")
        pdf.add_image_if_exists(preview_path, w=80,
                                caption=f"Figure: Ground overlay preview (Round {rn})")

        # Omni review
        pdf.section_title("    Step 4: Omni Review", level=3)
        reviews = rd["overlay_reviews"]
        if reviews:
            rev = reviews[0]
            status = "PASS" if rev["passed"] else "FAIL"
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 128, 0) if rev["passed"] else pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 6, f"Verdict: {status}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(50, 50, 50)

            review_text = rev["review"]
            if "MISSING" in review_text or "OVERCOVER" in review_text:
                pdf.body_text("Corrections suggested:")
                for line in review_text.split("\n"):
                    line = line.strip()
                    if line.startswith("MISSING") or line.startswith("OVERCOVER"):
                        pdf.body_text(f"  {line}")

            # For alley round 2, the review is detailed
            if rev["passed"]:
                pdf.body_text("Detailed review:")
                # Truncate for readability
                pdf.body_text(review_text[:500])

    # Final result for alley
    pdf.add_page()
    pdf.section_title("  Alley - Final Result", level=2)
    pdf.body_text(f"Final walkable mask: alley_walkable_mask.png")
    pdf.body_text(f"Coverage: {alley['final_result']['coverage_pct']:.1f}%")
    pdf.body_text(f"Rounds: {alley['final_result']['total_rounds']}")

    final_preview = os.path.join(LOG_DIR, "alley_final_preview.png")
    pdf.add_image_if_exists(final_preview, w=90,
                            caption="Figure: Final alley ground mask overlay")

    # ── Section 5: Summary ──
    pdf.add_page()
    pdf.section_title("5. Summary & Results")

    pdf.body_text("Iterative Ground Detection Results:")
    pdf.ln(2)

    # Results table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(35, 7, "Scene", border=1, fill=True)
    pdf.cell(25, 7, "Rounds", border=1, fill=True)
    pdf.cell(25, 7, "Coverage", border=1, fill=True)
    pdf.cell(35, 7, "Time", border=1, fill=True)
    pdf.cell(40, 7, "Output File", border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for scene_data in [("apartment", apt), ("alley", alley)]:
        sid, data = scene_data
        fr = data["final_result"]
        pdf.cell(35, 7, sid, border=1)
        pdf.cell(25, 7, str(fr["total_rounds"]), border=1)
        pdf.cell(25, 7, f'{fr["coverage_pct"]:.1f}%', border=1)
        pdf.cell(35, 7, fr["total_time"], border=1)
        pdf.cell(40, 7, f"{sid}_walkable_mask.png", border=1)
        pdf.ln()

    pdf.ln(5)
    pdf.section_title("Key Observations", level=2)
    pdf.body_text(
        "1. Apartment (3 rounds, 11.7% coverage):\n"
        "   - Round 1: Omni identified 4 patches at the bottom of the scene. SAM segmented them, "
        "but the review found OVERCOVER in the lower-left equipment area and MISSING in the central floor.\n"
        "   - Round 2: 4 new patches identified. Review still found overcover (table legs, cabinet) "
        "and missing areas (central floor).\n"
        "   - Round 3: 4 smaller patches along the bottom edge. Review PASSED.\n\n"
        "2. Alley (2 rounds, 15.4% coverage):\n"
        "   - Round 1: Omni identified 5 patches covering the wet路面 (road surface). Review found "
        "MISSING near the distant doorway and OVERCOVER on the right side (trash bins/walls).\n"
        "   - Round 2: 3 smaller patches filling gaps. Review PASSED with detailed confirmation "
        "that green overlay correctly covered the walkable path while avoiding obstacles.\n\n"
        "3. Error Handling:\n"
        "   - Alley Round 3 initially failed due to Omni API returning empty result. The script was "
        "patched with retry logic and graceful error handling.\n"
        "   - MobileSAM v2 models were unavailable; fell back to v1 (from R2 storage).\n\n"
        "4. Observations on the Pipeline:\n"
        "   - Omni tends to propose patches near the bottom of the image (closest to camera).\n"
        "   - SAM segmentation quality depends heavily on bbox precision.\n"
        "   - The iterative review process effectively catches false positives and gaps.\n"
        "   - Coverage percentages (11-15%) are appropriate for game walkable areas."
    )

    # ── Section 6: Appendix ──
    pdf.add_page()
    pdf.section_title("6. Appendix: Raw Data")
    pdf.body_text("Full JSON logs are available at:")
    pdf.body_text(f"  - {apt_log_path}")
    pdf.body_text(f"  - {alley_log_path}")
    pdf.body_text(f"\nAll intermediate images are saved in: {LOG_DIR}/")
    pdf.body_text("\nFiles generated per scene per round:")
    pdf.body_text("  - {scene}_r{round}_patch{N}_mask.png : Individual SAM mask")
    pdf.body_text("  - {scene}_round{round}_ground.png : Cumulative ground mask")
    pdf.body_text("  - {scene}_round{round}_preview.png : Overlay preview")
    pdf.body_text("  - {scene}_round{round}_review.png : Review visualization")
    pdf.body_text("  - {scene}_round{round}_context.png : Context with previous masks")
    pdf.body_text("  - {scene}_final_preview.png : Final result overlay")

    # Save
    pdf.output(OUTPUT_PDF)
    print(f"PDF generated: {OUTPUT_PDF}")
    print(f"  Pages: {pdf.page_no()}")
    print(f"  Size: {os.path.getsize(OUTPUT_PDF) / 1024:.1f} KB")


if __name__ == "__main__":
    build_report()
