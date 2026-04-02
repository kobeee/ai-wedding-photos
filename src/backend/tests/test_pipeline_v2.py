"""AI 管线重构可行性验证。

对比两种生成策略：
A. 一步法：多参考图 + prompt → 直接生成（当前方案）
B. 两步法：纯文本 → 底图 → repair_with_references 身份融合（重构方案）

用 VLM 质检对比两种方案的 identity_match / brief_alignment / aesthetic_score。
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# 确保能 import 项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.nano_banana import nano_banana_service
from services.vlm_checker import vlm_checker_service
from context.briefs import get_brief
from context.prompt_assembler import assemble_generation_prompt, assemble_nano_repair_prompt
from context.variant_planner import get_variants
from context.slot_renderer import render_slots
from context.reference_selector import select_references
from utils.storage import user_upload_dir


def _find_test_user() -> str:
    """找一个有上传图的用户。"""
    upload_base = Path(os.environ.get("UPLOAD_DIR", "./uploads"))
    if not upload_base.exists():
        raise RuntimeError(f"No uploads dir at {upload_base}")
    for d in upload_base.iterdir():
        if d.is_dir() and any(d.glob("*.png")) or any(d.glob("*.jpg")):
            return d.name
    raise RuntimeError("No user uploads found")


async def run_test():
    user_id = _find_test_user()
    print(f"测试用户: {user_id}")

    # 准备上下文
    upload_dir = user_upload_dir(user_id)
    ref_set = select_references(upload_dir)
    print(f"参考图: {ref_set.count} 张 (identity={ref_set.has_identity}, couple={ref_set.has_couple_identity})")

    if not ref_set.has_identity:
        print("没有身份参考图，无法对比身份保持能力，退出")
        return

    brief = get_brief("iceland")
    slots = render_slots(makeup_style="natural", gender="couple")
    variant = get_variants(brief, count=1)[0]
    prompt = assemble_generation_prompt(
        brief=brief,
        variant=variant,
        slots=slots,
        has_refs=ref_set.has_identity,
        has_couple_refs=ref_set.has_couple_identity,
        has_couple_anchor=ref_set.has_couple_anchor,
    )
    brief_summary = f"{brief.story} {brief.emotion}"
    selected_refs = ref_set.all_refs

    print(f"\n{'='*60}")
    print("策略 A：一步法（当前方案）— 参考图 + prompt 直接生成")
    print(f"{'='*60}")

    t0 = time.time()
    try:
        img_a = await nano_banana_service.multi_reference_generate(
            prompt=prompt,
            reference_images=selected_refs,
        )
        time_a = time.time() - t0
        print(f"生成成功，{len(img_a)} bytes，耗时 {time_a:.1f}s")
    except Exception as e:
        print(f"生成失败: {e}")
        return

    print(f"\n{'='*60}")
    print("策略 B：两步法 — 步骤1: 纯文本生成底图（无身份参考）")
    print(f"{'='*60}")

    prompt_no_identity = assemble_generation_prompt(
        brief=brief,
        variant=variant,
        slots=slots,
        has_refs=False,
        has_couple_refs=False,
        has_couple_anchor=False,
    )

    t0 = time.time()
    try:
        img_base = await nano_banana_service.text_to_image(
            prompt=prompt_no_identity,
        )
        time_b1 = time.time() - t0
        print(f"底图生成成功，{len(img_base)} bytes，耗时 {time_b1:.1f}s")
    except Exception as e:
        print(f"底图生成失败: {e}")
        return

    print(f"\n步骤2: repair_with_references 身份融合")

    fusion_prompt = assemble_nano_repair_prompt(
        render_prompt=prompt,
        repair_hints=[
            "Replace the generic faces with the exact facial identity from the reference photos",
            "Match skin tone, facial structure, and body proportions to reference photos",
            "Keep the scene, composition, lighting, and wardrobe exactly as they are",
        ],
        has_identity_refs=True,
        focus="physical",
    )

    t0 = time.time()
    try:
        img_b = await nano_banana_service.repair_with_references(
            prompt=fusion_prompt,
            image_data=img_base,
            reference_images=selected_refs,
        )
        time_b2 = time.time() - t0
        print(f"身份融合成功，{len(img_b)} bytes，耗时 {time_b2:.1f}s")
    except Exception as e:
        print(f"身份融合失败: {e}")
        return

    print(f"\n{'='*60}")
    print("VLM 质检对比")
    print(f"{'='*60}")

    report_a, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
        image_data=img_a,
        original_prompt=prompt,
        brief_summary=brief_summary,
    )
    print(f"\n策略 A（一步法）:")
    print(f"  identity_match:  {report_a.identity_match:.2f}")
    print(f"  brief_alignment: {report_a.brief_alignment:.2f}")
    print(f"  aesthetic_score:  {report_a.aesthetic_score:.2f}")
    print(f"  hard_fail:       {report_a.hard_fail}")
    print(f"  综合分:          {report_a.score:.2f}")
    print(f"  耗时:            {time_a:.1f}s")
    if report_a.issues:
        print(f"  issues: {[i.description for i in report_a.issues]}")

    report_b, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
        image_data=img_b,
        original_prompt=prompt,
        brief_summary=brief_summary,
    )
    print(f"\n策略 B（两步法）:")
    print(f"  identity_match:  {report_b.identity_match:.2f}")
    print(f"  brief_alignment: {report_b.brief_alignment:.2f}")
    print(f"  aesthetic_score:  {report_b.aesthetic_score:.2f}")
    print(f"  hard_fail:       {report_b.hard_fail}")
    print(f"  综合分:          {report_b.score:.2f}")
    print(f"  耗时:            {time_b1:.1f}s + {time_b2:.1f}s = {time_b1 + time_b2:.1f}s")
    if report_b.issues:
        print(f"  issues: {[i.description for i in report_b.issues]}")

    # 也单独质检底图（没有身份融合前）
    report_base, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
        image_data=img_base,
        original_prompt=prompt_no_identity,
        brief_summary=brief_summary,
    )
    print(f"\n底图（融合前，参考用）:")
    print(f"  identity_match:  {report_base.identity_match:.2f}")
    print(f"  brief_alignment: {report_base.brief_alignment:.2f}")
    print(f"  aesthetic_score:  {report_base.aesthetic_score:.2f}")

    print(f"\n{'='*60}")
    print("结论")
    print(f"{'='*60}")
    diff_id = report_b.identity_match - report_a.identity_match
    diff_brief = report_b.brief_alignment - report_a.brief_alignment
    diff_aes = report_b.aesthetic_score - report_a.aesthetic_score
    print(f"身份保持差异: {diff_id:+.2f} (B-A)")
    print(f"创意匹配差异: {diff_brief:+.2f} (B-A)")
    print(f"美学评分差异: {diff_aes:+.2f} (B-A)")
    print(f"延迟差异:     一步={time_a:.1f}s  两步={time_b1+time_b2:.1f}s")

    # 保存结果图以便人工检查
    out_dir = Path("./test_outputs")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "A_one_shot.png").write_bytes(img_a)
    (out_dir / "B_base_no_identity.png").write_bytes(img_base)
    (out_dir / "B_fused.png").write_bytes(img_b)
    print(f"\n结果图已保存到 {out_dir.resolve()}/")


if __name__ == "__main__":
    asyncio.run(run_test())
