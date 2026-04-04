"""V5 多维矩阵 Harness — 系统化测试 AI 管线的跨场景通用能力。

设计思路：
  - 24 个测试 case 覆盖 10 套餐 × close/medium/wide × couple/female/male
  - 每个 case 自动从生产代码组装三轮 prompt（不再手写覆盖）
  - 结构化 JSON 报告，直接喂给 Codex 评审
  - 支持按维度过滤（套餐/构图/性别）只跑子集
  - 所有 prompt 走 prompt_assembler 生产路径，harness 不再有独立模板

用法：
  python harness.py                          # 跑全部 24 case
  python harness.py --package iceland        # 只跑 iceland
  python harness.py --framing close          # 只跑 close-up
  python harness.py --gender female          # 只跑 solo bride
  python harness.py --case iceland_intimate_couple  # 跑单个 case
  python harness.py --list                   # 列出所有 case
  python harness.py --dry-run               # 只生成 prompt，不调 API
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.nano_banana import nano_banana_service
from context.briefs import get_brief, CreativeBrief
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_nano_repair_prompt,
    assemble_identity_fusion_prompt,
    SYSTEM_IDENTITY_PHOTOGRAPHER,
    R2_COMPOSITION_LOCK,
)
from context.variant_planner import get_variants
from context.slot_renderer import render_slots
from context.reference_selector import select_references

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(os.environ.get(
    "UPLOAD_DIR",
    str(Path(__file__).resolve().parent.parent / "uploads"),
))
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "harness_outputs"
USER_ID = "c93348267c8b"  # 5 张参考图��测试用户

# ---------------------------------------------------------------------------
# 测试矩阵定义
# ---------------------------------------------------------------------------

# 24 个 case，覆盖维度：
# - 10 套餐全覆盖（每个至少 2 case）
# - close/medium/wide 各 ~8 个
# - couple 16 / female 4 / male 4
# - 光照 warm/cool/neon/contrast 自然跟随套餐
# - 难度 高(奇幻/赛博/极简) / 中(中日西) / 低(法式/旅拍/星空)

MATRIX: list[dict] = [
    # --- iceland (cool_diffused, tender) ---
    {"package": "iceland",           "variant_idx": 0, "gender": "couple",  "tag": "close+cool"},
    {"package": "iceland",           "variant_idx": 1, "gender": "couple",  "tag": "wide+cool"},
    {"package": "iceland",           "variant_idx": 2, "gender": "female",  "tag": "medium+cool+solo"},

    # --- cyberpunk (neon_reflective, dramatic) ---
    {"package": "cyberpunk",         "variant_idx": 0, "gender": "couple",  "tag": "close+neon"},
    {"package": "cyberpunk",         "variant_idx": 1, "gender": "couple",  "tag": "wide+neon"},
    {"package": "cyberpunk",         "variant_idx": 2, "gender": "male",    "tag": "medium+neon+solo"},

    # --- french (soft_warm, natural) ---
    {"package": "french",            "variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},
    {"package": "french",            "variant_idx": 3, "gender": "couple",  "tag": "close+warm"},
    {"package": "french",            "variant_idx": 1, "gender": "female",  "tag": "medium+warm+solo"},

    # --- minimal (high_contrast, still) ---
    {"package": "minimal",           "variant_idx": 0, "gender": "couple",  "tag": "wide+contrast"},
    {"package": "minimal",           "variant_idx": 2, "gender": "couple",  "tag": "medium+contrast"},
    {"package": "minimal",           "variant_idx": 1, "gender": "male",    "tag": "close+contrast+solo"},

    # --- onsen (soft_warm, still) ---
    {"package": "onsen",             "variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},
    {"package": "onsen",             "variant_idx": 3, "gender": "couple",  "tag": "close+warm"},

    # --- starcamp (soft_warm, playful) ---
    {"package": "starcamp",          "variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},
    {"package": "starcamp",          "variant_idx": 2, "gender": "female",  "tag": "medium+warm+solo"},

    # --- chinese-classic (soft_warm, tender) ---
    {"package": "chinese-classic",   "variant_idx": 1, "gender": "couple",  "tag": "close+warm"},
    {"package": "chinese-classic",   "variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},

    # --- western-romantic (soft_warm, tender) ---
    {"package": "western-romantic",  "variant_idx": 2, "gender": "couple",  "tag": "close+warm"},
    {"package": "western-romantic",  "variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},

    # --- artistic-fantasy (cool_diffused, dramatic) ---
    {"package": "artistic-fantasy",  "variant_idx": 0, "gender": "couple",  "tag": "wide+cool"},
    {"package": "artistic-fantasy",  "variant_idx": 2, "gender": "male",    "tag": "close+cool+solo"},

    # --- travel-destination (soft_warm, playful) ---
    {"package": "travel-destination","variant_idx": 0, "gender": "couple",  "tag": "wide+warm"},
    {"package": "travel-destination","variant_idx": 2, "gender": "female",  "tag": "medium+warm+solo"},
]


def _case_id(entry: dict) -> str:
    brief = get_brief(entry["package"])
    variants = get_variants(brief, count=4)
    v = variants[entry["variant_idx"] % len(variants)]
    return f"{entry['package']}_{v.id}_{entry['gender']}"


def _framing_of(entry: dict) -> str:
    brief = get_brief(entry["package"])
    variants = get_variants(brief, count=4)
    v = variants[entry["variant_idx"] % len(variants)]
    return v.framing


# ---------------------------------------------------------------------------
# R2 精修 prompt（标准化，走生产代码）
# ---------------------------------------------------------------------------

_R2_STANDARD_HINTS_COUPLE = [
    "Refine ONLY within the existing frame — do NOT change the crop, zoom, or composition",
    "Improve wardrobe texture: fabric weave, draping, stitching detail",
    "Fix hand anatomy — all fingers clearly defined with natural joints",
    "Add realistic skin texture: visible pores, natural imperfections",
    "Enhance couple interaction — make it feel genuine and emotionally intimate",
]

_R2_STANDARD_HINTS_SOLO = [
    "Refine ONLY within the existing frame — do NOT change the crop, zoom, or composition",
    "Improve wardrobe texture: fabric weave, draping, stitching detail",
    "Fix hand anatomy — all fingers clearly defined with natural joints",
    "Add realistic skin texture: visible pores, natural imperfections",
    "Enhance the subject's expression and emotional presence",
]


def _build_r2_prompt(brief: CreativeBrief, slots, gender: str = "couple") -> str:
    """标准 R2 精修 prompt，走 assemble_nano_repair_prompt 生产路径。"""
    is_solo = gender in ("female", "male")

    # wardrobe 按性别条件渲染
    wardrobe_parts = []
    if gender in ("couple", "female") and brief.wardrobe_bride:
        wardrobe_parts.append(brief.wardrobe_bride)
    if gender in ("couple", "male") and brief.wardrobe_groom:
        wardrobe_parts.append(brief.wardrobe_groom)
    wardrobe_text = " / ".join(wardrobe_parts) if wardrobe_parts else ""

    hints = _R2_STANDARD_HINTS_SOLO if is_solo else _R2_STANDARD_HINTS_COUPLE

    return assemble_nano_repair_prompt(
        render_prompt=(
            f"{brief.story} {brief.visual_essence} "
            f"Wardrobe: {wardrobe_text}. "
            f"Makeup: {slots.makeup or brief.makeup_default}."
        ),
        repair_hints=hints,
        has_identity_refs=False,
        focus="physical",
        gender=gender,
    )


# ---------------------------------------------------------------------------
# 三轮生图核心（使用生产代码 prompt assembler）
# ---------------------------------------------------------------------------

async def run_case(entry: dict, *, dry_run: bool = False) -> dict:
    """执行单个测试 case 的三轮迭代生图。"""

    case_id = _case_id(entry)
    package_id = entry["package"]
    gender = entry["gender"]
    variant_idx = entry["variant_idx"]

    # 准备参考图（按 gender 过滤，solo 场景只取对应性别）
    upload_dir = UPLOAD_DIR / USER_ID
    ref_set = select_references(upload_dir, gender=gender) if upload_dir.exists() else None

    if ref_set and not ref_set.has_identity:
        ref_set = None

    has_refs = ref_set is not None and ref_set.has_identity
    has_couple_refs = ref_set.has_couple_identity if ref_set else False
    has_couple_anchor = ref_set.has_couple_anchor if ref_set else False

    # 构建 brief + slots + variant
    brief = get_brief(package_id)
    slots = render_slots(makeup_style="natural", gender=gender)
    variants = get_variants(brief, count=max(variant_idx + 1, 4))
    variant = variants[variant_idx % len(variants)]

    print(f"\n{'='*60}")
    print(f"Case: {case_id}")
    print(f"  套餐={package_id}  构图={variant.framing}  性别={gender}")
    print(f"  变体={variant.id}: {variant.intent}")
    if ref_set:
        print(f"  参考图: {ref_set.count} 张 (roles={ref_set.selected_role_counts})")
    else:
        print(f"  参考图: 无（风格样片模式）")
    print(f"{'='*60}")

    # 输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"v5_{case_id}_{ts}"

    result = {
        "case_id": case_id,
        "package": package_id,
        "variant_id": variant.id,
        "framing": variant.framing,
        "gender": gender,
        "tag": entry.get("tag", ""),
        "lighting": brief.lighting_bias,
        "pose_energy": brief.pose_energy,
        "rounds": [],
        "status": "pending",
    }

    # =========================================================
    # Round 1: text_to_image — 纯��景底图（无参考图，不扛身份压力）
    # =========================================================
    r1_prompt = assemble_generation_prompt(
        brief=brief,
        variant=variant,
        slots=slots,
        has_refs=False,
        has_couple_refs=False,
        has_couple_anchor=False,
        gender=gender,
    )
    result["prompts"] = {"r1": r1_prompt}

    print(f"\n  --- R1: 场景底图 (text_to_image) ---")
    print(f"  prompt ({len(r1_prompt)} chars): {r1_prompt[:150]}...")

    if dry_run:
        result["status"] = "dry_run"
        result["rounds"] = [{"round": 1, "status": "skipped"}]
        _save_meta(prefix, result, {"r1": r1_prompt})
        return result

    t0 = time.time()
    try:
        r1_img = await nano_banana_service.text_to_image(prompt=r1_prompt)
        r1_time = time.time() - t0
        r1_path = OUTPUT_DIR / f"{prefix}_R1.png"
        r1_path.write_bytes(r1_img)
        print(f"  R1 OK: {len(r1_img)} bytes, {r1_time:.1f}s → {r1_path.name}")
        result["rounds"].append({
            "round": 1, "status": "ok", "bytes": len(r1_img),
            "elapsed": round(r1_time, 1), "path": str(r1_path),
        })
    except Exception as e:
        print(f"  R1 FAILED: {e}")
        result["status"] = "failed_r1"
        result["error"] = str(e)
        _save_meta(prefix, result, {"r1": r1_prompt})
        return result

    # =========================================================
    # Round 2: image_to_image — 服饰/动作精修（构图锁定）
    # =========================================================
    r2_prompt = _build_r2_prompt(brief, slots, gender=gender)
    result["prompts"]["r2"] = r2_prompt

    print(f"\n  --- R2: 细节精修 (image_to_image, 构图锁定) ---")
    print(f"  prompt ({len(r2_prompt)} chars): {r2_prompt[:150]}...")

    t0 = time.time()
    try:
        r2_img = await nano_banana_service.image_to_image(
            prompt=r2_prompt,
            image_data=r1_img,
        )
        r2_time = time.time() - t0
        r2_path = OUTPUT_DIR / f"{prefix}_R2.png"
        r2_path.write_bytes(r2_img)
        print(f"  R2 OK: {len(r2_img)} bytes, {r2_time:.1f}s → {r2_path.name}")
        result["rounds"].append({
            "round": 2, "status": "ok", "bytes": len(r2_img),
            "elapsed": round(r2_time, 1), "path": str(r2_path),
        })
    except Exception as e:
        print(f"  R2 FAILED: {e}")
        result["status"] = "failed_r2"
        result["error"] = str(e)
        _save_meta(prefix, result, result["prompts"])
        return result

    # =========================================================
    # Round 3: multi_reference_generate — 身份融合（生成语义）
    # =========================================================
    r3_prompt = assemble_identity_fusion_prompt(
        brief=brief,
        variant=variant,
        gender=gender,
    )
    result["prompts"]["r3"] = r3_prompt

    print(f"\n  --- R3: 身份融合 (multi_reference_generate, 生成语义) ---")
    print(f"  prompt ({len(r3_prompt)} chars): {r3_prompt[:150]}...")

    if not has_refs:
        # 无参考图 → 跳过 R3，R2 即为最终成果
        print(f"  ⚠ 无身份参考图，跳过 R3，R2 即最终成果")
        result["rounds"].append({"round": 3, "status": "skipped_no_refs"})
        result["status"] = "ok_r2_only"
        result["final_image"] = str(r2_path)
        _save_meta(prefix, result, result["prompts"])
        return result

    # R3 参考图排列：R2 成品（构图锚定） + 身份参考图
    r3_refs: list[tuple[bytes, str]] = [
        (r2_img, "image/png"),
    ] + ref_set.all_refs

    print(f"  R3 参考图: {len(r3_refs)} 张 (1=���图 + {ref_set.count}=身份)")

    t0 = time.time()
    try:
        r3_img = await nano_banana_service.multi_reference_generate(
            prompt=r3_prompt,
            reference_images=r3_refs,
        )
        r3_time = time.time() - t0
        r3_path = OUTPUT_DIR / f"{prefix}_R3.png"
        r3_path.write_bytes(r3_img)
        print(f"  R3 OK: {len(r3_img)} bytes, {r3_time:.1f}s → {r3_path.name}")
        result["rounds"].append({
            "round": 3, "status": "ok", "bytes": len(r3_img),
            "elapsed": round(r3_time, 1), "path": str(r3_path),
        })
    except Exception as e:
        print(f"  R3 FAILED: {e}")
        result["status"] = "failed_r3"
        result["error"] = str(e)
        _save_meta(prefix, result, result["prompts"])
        return result

    # 汇总
    total_time = sum(r["elapsed"] for r in result["rounds"] if "elapsed" in r)
    result["status"] = "ok"
    result["total_elapsed"] = round(total_time, 1)
    result["cost_estimate"] = f"~${len([r for r in result['rounds'] if r['status'] == 'ok']) * 0.13:.2f}"
    result["final_image"] = str(r3_path)

    _save_meta(prefix, result, result["prompts"])

    print(f"\n  总耗时: {total_time:.1f}s, 预估成本: {result['cost_estimate']}")
    print(f"  最终成片: {r3_path}")

    return result


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _save_meta(prefix: str, result: dict, prompts: dict):
    """保存实验元数据和 prompt 到文件。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    meta_path = OUTPUT_DIR / f"{prefix}_meta.json"
    # 不保存 prompts 到 meta（太大），单独保存
    meta = {k: v for k, v in result.items() if k != "prompts"}
    meta["timestamp"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    prompt_path = OUTPUT_DIR / f"{prefix}_prompts.json"
    prompt_path.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_codex_review_manifest(results: list[dict], batch_ts: str) -> Path:
    """生成 Codex 评审清单 JSON。"""
    manifest = {
        "harness_version": "v5_matrix",
        "batch_timestamp": batch_ts,
        "total_cases": len(results),
        "succeeded": len([r for r in results if r["status"].startswith("ok")]),
        "failed": len([r for r in results if r["status"].startswith("failed")]),
        "cases": [],
    }

    for r in results:
        case_entry = {
            "case_id": r["case_id"],
            "package": r["package"],
            "variant_id": r.get("variant_id", ""),
            "framing": r.get("framing", ""),
            "gender": r["gender"],
            "tag": r.get("tag", ""),
            "lighting": r.get("lighting", ""),
            "status": r["status"],
            "final_image": r.get("final_image", ""),
            "total_elapsed": r.get("total_elapsed", 0),
            "cost_estimate": r.get("cost_estimate", ""),
        }
        manifest["cases"].append(case_entry)

    # 维度统计
    manifest["dimension_stats"] = {
        "by_package": _group_stats(results, "package"),
        "by_framing": _group_stats(results, "framing"),
        "by_gender": _group_stats(results, "gender"),
        "by_lighting": _group_stats(results, "lighting"),
    }

    manifest_path = OUTPUT_DIR / f"v5_batch_{batch_ts}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def _group_stats(results: list[dict], key: str) -> dict:
    groups: dict[str, dict] = {}
    for r in results:
        val = r.get(key, "unknown")
        if val not in groups:
            groups[val] = {"total": 0, "ok": 0, "failed": 0}
        groups[val]["total"] += 1
        if r["status"].startswith("ok"):
            groups[val]["ok"] += 1
        elif r["status"].startswith("failed"):
            groups[val]["failed"] += 1
    return groups


# ---------------------------------------------------------------------------
# 批跑入口
# ---------------------------------------------------------------------------

async def run_batch(cases: list[dict], *, dry_run: bool = False) -> list[dict]:
    """顺序执行一批测试 case。"""
    results = []
    for i, entry in enumerate(cases):
        cid = _case_id(entry)
        print(f"\n{'#'*60}")
        print(f"# [{i+1}/{len(cases)}] {cid}")
        print(f"{'#'*60}")

        try:
            result = await run_case(entry, dry_run=dry_run)
            results.append(result)
        except Exception as e:
            print(f"  FATAL ERROR: {e}")
            results.append({
                "case_id": cid,
                "package": entry["package"],
                "gender": entry["gender"],
                "status": "fatal_error",
                "error": str(e),
            })

        # API 友好间隔（避免 rate limit）
        if not dry_run and i < len(cases) - 1:
            print(f"  等待 3s 再跑下一个...")
            await asyncio.sleep(3)

    return results


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="V5 多维矩阵 Harness")
    parser.add_argument("--package", help="只跑指定套餐")
    parser.add_argument("--framing", help="只跑指定构图 (close/medium/wide)")
    parser.add_argument("--gender", help="只跑指定性别 (couple/female/male)")
    parser.add_argument("--case", help="只跑指定 case_id")
    parser.add_argument("--list", action="store_true", help="列出所有 case 不执行")
    parser.add_argument("--dry-run", action="store_true", help="只生成 prompt 不调 API")
    return parser.parse_args()


def filter_cases(args) -> list[dict]:
    cases = list(MATRIX)
    if args.case:
        cases = [e for e in cases if _case_id(e) == args.case]
    if args.package:
        cases = [e for e in cases if e["package"] == args.package]
    if args.framing:
        cases = [e for e in cases if _framing_of(e) == args.framing]
    if args.gender:
        cases = [e for e in cases if e["gender"] == args.gender]
    return cases


async def main():
    args = parse_args()
    cases = filter_cases(args)

    if not cases:
        print("没有匹配的 case。用 --list 查看所有 case。")
        sys.exit(1)

    if args.list:
        print(f"共 {len(cases)} 个 case:\n")
        print(f"{'CASE_ID':<50} {'FRAMING':<10} {'GENDER':<10} {'TAG'}")
        print("-" * 90)
        for e in cases:
            cid = _case_id(e)
            framing = _framing_of(e)
            print(f"{cid:<50} {framing:<10} {e['gender']:<10} {e.get('tag', '')}")

        # 维度统计
        print(f"\n--- 维度覆盖统计 ---")
        packages = set(e["package"] for e in cases)
        framings = set(_framing_of(e) for e in cases)
        genders = set(e["gender"] for e in cases)
        print(f"  套餐 ({len(packages)}): {', '.join(sorted(packages))}")
        print(f"  构图 ({len(framings)}): {', '.join(sorted(framings))}")
        print(f"  性别 ({len(genders)}): {', '.join(sorted(genders))}")
        return

    batch_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"V5 矩阵 Harness — {len(cases)} 个 case，batch={batch_ts}")
    if args.dry_run:
        print("*** DRY RUN 模式 — 只生成 prompt，不调 API ***")

    results = await run_batch(cases, dry_run=args.dry_run)

    # 生成评审清单
    manifest_path = _build_codex_review_manifest(results, batch_ts)

    # 汇总
    ok = len([r for r in results if r["status"].startswith("ok")])
    failed = len([r for r in results if r["status"].startswith("failed")])
    total_time = sum(r.get("total_elapsed", 0) for r in results)
    total_cost = sum(
        float(r.get("cost_estimate", "~$0").replace("~$", ""))
        for r in results if r.get("cost_estimate")
    )

    print(f"\n{'='*60}")
    print(f"V5 批跑完成")
    print(f"  成功: {ok}/{len(results)}")
    print(f"  失败: {failed}/{len(results)}")
    print(f"  总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  总成本: ~${total_cost:.2f}")
    print(f"  评审清单: {manifest_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
