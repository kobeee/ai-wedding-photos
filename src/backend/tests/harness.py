"""V7 双轨 Harness — 测试完整生产管线（validation track + hero track + face lock + VLM）。

SSS 目标 Harness：
  - 测试 production_orchestrator.run_photo()，即真实生产路径
  - 每个 case 输出：validation 图 + hero 图 + VLM 质检报告 + 多维评分
  - 评分维度：identity_verifiability / proportion_verifiability / hero_quality / commercial_pass
  - 结构化 JSON 报告，直接喂给 Codex 评审
  - 支持 --dry-run（只生成 prompt，不调 API）
  - 支持 --editorial-only（只跑 editorial pipeline，跳过双轨编排）

用法：
  python harness.py                          # 跑全部 24 case
  python harness.py --package iceland        # 只跑 iceland
  python harness.py --framing close          # 只跑 close-up
  python harness.py --gender female          # 只跑 solo bride
  python harness.py --case iceland_intimate_couple  # 跑单个 case
  python harness.py --list                   # 列出所有 case
  python harness.py --dry-run               # 只生成 prompt，不调 API
  python harness.py --editorial-only         # 只跑 R1-R4，不经双轨编排
  python harness.py --quick                  # 只跑 3 个代表性 case（快速验证）
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

from context.briefs import get_brief, CreativeBrief
from context.prompt_assembler import assemble_generation_prompt
from context.variant_planner import get_variants
from context.slot_renderer import render_slots
from context.reference_selector import select_references
from services.editorial_pipeline import run_editorial_pipeline
from services.makeup_reference import resolve_selected_makeup_reference, MakeupReference

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(os.environ.get(
    "UPLOAD_DIR",
    str(Path(__file__).resolve().parent.parent / "uploads"),
))
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "harness_outputs"
USER_ID = "c93348267c8b"  # 5 张参考图的测试用户

# ---------------------------------------------------------------------------
# 测试矩阵定义
# ---------------------------------------------------------------------------

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

# 快速验证子集：3 个代表性 case（couple+close, couple+wide, solo+medium）
QUICK_MATRIX: list[dict] = [
    {"package": "french",            "variant_idx": 3, "gender": "couple",  "tag": "close+warm+quick"},
    {"package": "iceland",           "variant_idx": 1, "gender": "couple",  "tag": "wide+cool+quick"},
    {"package": "iceland",           "variant_idx": 2, "gender": "female",  "tag": "medium+cool+solo+quick"},
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
# V7 双轨生图核心（使用 production_orchestrator）
# ---------------------------------------------------------------------------

async def run_case(entry: dict, *, dry_run: bool = False, editorial_only: bool = False) -> dict:
    """执行单个测试 case。

    默认走 production_orchestrator（完整双轨管线）。
    --editorial-only 时走 editorial_pipeline（仅 R1-R4）。
    """
    case_id = _case_id(entry)
    package_id = entry["package"]
    gender = entry["gender"]
    variant_idx = entry["variant_idx"]

    # 准备参考图
    upload_dir = UPLOAD_DIR / USER_ID
    ref_set = select_references(upload_dir, gender=gender) if upload_dir.exists() else None
    if ref_set and not ref_set.has_identity:
        ref_set = None

    has_refs = ref_set is not None and ref_set.has_identity

    bride_makeup_style = "refined" if gender in {"couple", "female"} else None
    groom_makeup_style = "natural" if gender in {"couple", "male"} else None

    # 构建 brief + slots + variant
    brief = get_brief(package_id)
    slots = render_slots(
        makeup_style="natural",
        gender=gender,
        bride_makeup_style=bride_makeup_style,
        groom_makeup_style=groom_makeup_style,
    )
    variants = get_variants(brief, count=max(variant_idx + 1, 4))
    variant = variants[variant_idx % len(variants)]

    bride_makeup_ref: MakeupReference | None = None
    groom_makeup_ref: MakeupReference | None = None
    if not dry_run:
        if gender in {"couple", "female"}:
            bride_makeup_ref = await resolve_selected_makeup_reference(
                USER_ID, "female", bride_makeup_style, None,
            )
        if gender in {"couple", "male"}:
            groom_makeup_ref = await resolve_selected_makeup_reference(
                USER_ID, "male", groom_makeup_style, None,
            )

    mode = "editorial_only" if editorial_only else "production_orchestrator"
    print(f"\n{'='*60}")
    print(f"Case: {case_id}  [{mode}]")
    print(f"  套餐={package_id}  构图={variant.framing}  性别={gender}")
    print(f"  变体={variant.id}: {variant.intent}")
    if ref_set:
        print(f"  参考图: {ref_set.count} 张 (roles={ref_set.selected_role_counts})")
    else:
        print(f"  参考图: 无（风格样片模式）")
    print(f"{'='*60}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"v7_{case_id}_{ts}"

    result: dict = {
        "case_id": case_id,
        "package": package_id,
        "variant_id": variant.id,
        "framing": variant.framing,
        "gender": gender,
        "tag": entry.get("tag", ""),
        "lighting": brief.lighting_bias,
        "pose_energy": brief.pose_energy,
        "bride_makeup_style": bride_makeup_style,
        "groom_makeup_style": groom_makeup_style,
        "mode": mode,
        "status": "pending",
    }

    # Dry-run：生成 prompt 但不调 API
    if dry_run:
        r1_prompt = assemble_generation_prompt(
            brief=brief, variant=variant, slots=slots,
            has_refs=False, has_couple_refs=False,
            has_couple_anchor=bool(ref_set and ref_set.structure_refs) and gender == "couple",
            gender=gender, identity_priority=has_refs, track="hero",
        )
        r1_val_prompt = assemble_generation_prompt(
            brief=brief, variant=variant, slots=slots,
            has_refs=False, has_couple_refs=False,
            has_couple_anchor=bool(ref_set and ref_set.structure_refs) and gender == "couple",
            gender=gender, identity_priority=has_refs, track="validation",
        )
        result["prompts"] = {
            "r1_hero": r1_prompt,
            "r1_validation": r1_val_prompt,
            "r1_validation_diff_chars": len(r1_val_prompt) - len(r1_prompt),
        }
        result["status"] = "dry_run"
        _save_meta(prefix, result, result["prompts"])
        print(f"  [DRY RUN] Hero prompt: {len(r1_prompt)} chars")
        print(f"  [DRY RUN] Validation prompt: {len(r1_val_prompt)} chars (+{len(r1_val_prompt) - len(r1_prompt)})")
        return result

    t0 = time.time()

    if editorial_only:
        return await _run_editorial_only(
            entry=entry, brief=brief, variant=variant, slots=slots, gender=gender,
            ref_set=ref_set, has_refs=has_refs,
            bride_makeup_ref=bride_makeup_ref, groom_makeup_ref=groom_makeup_ref,
            result=result, prefix=prefix, t0=t0,
        )

    # --- 完整双轨管线 ---
    return await _run_production_orchestrator(
        brief=brief, variant=variant, slots=slots, gender=gender,
        ref_set=ref_set,
        bride_makeup_ref=bride_makeup_ref, groom_makeup_ref=groom_makeup_ref,
        result=result, prefix=prefix, t0=t0,
    )


async def _run_production_orchestrator(
    *,
    brief: CreativeBrief, variant, slots, gender: str,
    ref_set, bride_makeup_ref, groom_makeup_ref,
    result: dict, prefix: str, t0: float,
) -> dict:
    """使用 production_orchestrator 跑完整双轨管线。"""
    from services.production_orchestrator import production_orchestrator_service

    try:
        orchestrated = await production_orchestrator_service.run_photo(
            brief=brief,
            hero_variant=variant,
            slots=slots,
            gender=gender,
            ref_set=ref_set,
            bride_makeup_ref=bride_makeup_ref,
            groom_makeup_ref=groom_makeup_ref,
        )
        total_elapsed = time.time() - t0
    except Exception as e:
        print(f"  PRODUCTION PIPELINE FAILED: {e}")
        result["status"] = "failed_pipeline"
        result["error"] = str(e)
        result["total_elapsed"] = round(time.time() - t0, 1)
        _save_meta(prefix, result, {})
        return result

    # 保存所有资产
    assets_data: list[dict] = []
    for i, asset in enumerate(orchestrated.assets):
        asset_filename = f"{prefix}_{asset.track.value}_{asset.kind.value}_{i}.png"
        asset_path = OUTPUT_DIR / asset_filename
        asset_path.write_bytes(asset.image_data)

        asset_info = {
            "index": i,
            "track": asset.track.value,
            "kind": asset.kind.value,
            "quality_score": asset.quality_score,
            "user_visible": asset.user_visible,
            "verifiability": {
                "is_identity_verifiable": asset.verifiability.is_identity_verifiable,
                "is_proportion_verifiable": asset.verifiability.is_proportion_verifiable,
                "face_area_ratio_bride": asset.verifiability.face_area_ratio_bride,
                "face_area_ratio_groom": asset.verifiability.face_area_ratio_groom,
                "body_visibility_score": asset.verifiability.body_visibility_score,
                "notes": asset.verifiability.notes,
            },
            "notes": asset.notes,
            "path": str(asset_path),
            "bytes": len(asset.image_data),
        }
        assets_data.append(asset_info)
        visible_tag = " [VISIBLE]" if asset.user_visible else " [HIDDEN]"
        print(
            f"  Asset {i}: {asset.track.value}/{asset.kind.value} "
            f"score={asset.quality_score:.2f} "
            f"id_verify={asset.verifiability.is_identity_verifiable} "
            f"prop_verify={asset.verifiability.is_proportion_verifiable} "
            f"face_bride={asset.verifiability.face_area_ratio_bride:.3f} "
            f"face_groom={asset.verifiability.face_area_ratio_groom:.3f}"
            f"{visible_tag} → {asset_path.name}"
        )

    # 多维评分
    scoring = _compute_sss_scoring(assets_data, gender)

    result["assets"] = assets_data
    result["scoring"] = scoring
    result["total_elapsed"] = round(total_elapsed, 1)
    result["asset_count"] = len(assets_data)
    result["visible_count"] = len([a for a in assets_data if a["user_visible"]])
    result["status"] = "ok" if scoring["commercial_pass"] else "ok_but_below_sss"

    cost_per_api_call = 0.13
    # 估算：validation(4轮) + hero(4轮) + VLM(~3次) + face_lock(~2次) ≈ 12 calls
    estimated_calls = 12
    result["cost_estimate"] = f"~${estimated_calls * cost_per_api_call:.2f}"

    _save_meta(prefix, result, {})

    print(f"\n  --- SSS 评分 ---")
    print(f"  identity_verifiability: {'PASS' if scoring['identity_verifiability'] else 'FAIL'}")
    print(f"  proportion_verifiability: {'PASS' if scoring['proportion_verifiability'] else 'FAIL'}")
    print(f"  hero_track_ok: {'YES' if scoring['hero_track_ok'] else 'NO (validation promoted)'}")
    print(f"  hero_quality: {scoring['hero_quality']:.2f}" + (" (no hero)" if not scoring['hero_track_ok'] else ""))
    print(f"  delivery_quality: {scoring['delivery_quality']:.2f}")
    print(f"  commercial_pass: {'PASS' if scoring['commercial_pass'] else 'FAIL'}")
    print(f"  总耗时: {total_elapsed:.1f}s, 预估成本: {result['cost_estimate']}")

    return result


async def _run_editorial_only(
    *,
    entry: dict, brief: CreativeBrief, variant, slots, gender: str,
    ref_set, has_refs: bool, bride_makeup_ref, groom_makeup_ref,
    result: dict, prefix: str, t0: float,
) -> dict:
    """仅跑 editorial pipeline（R1-R4），用于对比或调试。"""
    try:
        pipeline_result = await run_editorial_pipeline(
            brief=brief, variant=variant, slots=slots, gender=gender,
            ref_set=ref_set if has_refs else None,
            bride_makeup_ref=bride_makeup_ref, groom_makeup_ref=groom_makeup_ref,
        )
        total_elapsed = time.time() - t0
    except Exception as e:
        print(f"  EDITORIAL PIPELINE FAILED: {e}")
        result["status"] = "failed_pipeline"
        result["error"] = str(e)
        _save_meta(prefix, result, {})
        return result

    result["prompts"] = pipeline_result.prompts
    result["rounds"] = []
    for round_index, round_result in enumerate(pipeline_result.rounds, start=1):
        round_path = OUTPUT_DIR / f"{prefix}_{round_result.key.upper()}.png"
        round_path.write_bytes(round_result.image_data)
        per_round_elapsed = round(total_elapsed / max(len(pipeline_result.rounds), 1), 1)
        print(
            f"  {round_result.key.upper()} OK: {len(round_result.image_data)} bytes, "
            f"refs={round_result.reference_count}, ~{per_round_elapsed:.1f}s → {round_path.name}"
        )
        result["rounds"].append({
            "round": round_index, "key": round_result.key, "status": "ok",
            "mode": round_result.mode, "bytes": len(round_result.image_data),
            "elapsed": per_round_elapsed, "reference_count": round_result.reference_count,
            "path": str(round_path),
        })

    total_time = sum(r["elapsed"] for r in result["rounds"] if "elapsed" in r)
    result["status"] = "ok"
    result["total_elapsed"] = round(total_time, 1)
    result["cost_estimate"] = f"~${len([r for r in result['rounds'] if r['status'] == 'ok']) * 0.13:.2f}"
    result["final_image"] = result["rounds"][-1]["path"]
    _save_meta(prefix, result, result.get("prompts", {}))
    print(f"\n  总耗时: {total_time:.1f}s, 预估成本: {result['cost_estimate']}")
    return result


# ---------------------------------------------------------------------------
# SSS 多维评分
# ---------------------------------------------------------------------------

def _compute_sss_scoring(assets: list[dict], gender: str) -> dict:
    """计算 SSS 多维评分。

    identity_verifiability: 至少 1 张 validation-safe 图且 is_identity_verifiable=true
    proportion_verifiability: 至少 1 张图 is_proportion_verifiable=true
    hero_track_ok: 是否有真正的 hero/face_lock 可见资产（不含 promoted validation）
    hero_quality: 真正 hero 图的平均 quality_score
    delivery_quality: 最终可见图的平均 quality_score（含 promoted validation）
    commercial_pass: identity + proportion + delivery_quality >= 0.85
    """
    validation_assets = [a for a in assets if a["track"] == "validation"]
    hero_assets = [a for a in assets if a["track"] in ("hero", "face_lock") and a["user_visible"]]

    identity_ok = any(
        a["verifiability"]["is_identity_verifiable"]
        for a in validation_assets
    )
    proportion_ok = any(
        a["verifiability"]["is_proportion_verifiable"]
        for a in validation_assets
    )

    # 真正的 hero track 质量
    hero_scores = [a["quality_score"] for a in hero_assets if a["quality_score"] > 0]
    hero_quality = sum(hero_scores) / len(hero_scores) if hero_scores else 0.0
    hero_track_ok = len(hero_assets) > 0

    # 最终可见图质量（含 promoted validation fallback）
    all_visible = [a for a in assets if a["user_visible"]]
    visible_scores = [a["quality_score"] for a in all_visible if a["quality_score"] > 0]
    delivery_quality = sum(visible_scores) / len(visible_scores) if visible_scores else 0.0

    commercial_pass = identity_ok and proportion_ok and delivery_quality >= 0.85

    return {
        "identity_verifiability": identity_ok,
        "proportion_verifiability": proportion_ok,
        "hero_track_ok": hero_track_ok,
        "hero_quality": round(hero_quality, 3),
        "delivery_quality": round(delivery_quality, 3),
        "commercial_pass": commercial_pass,
        "validation_asset_count": len(validation_assets),
        "hero_asset_count": len(hero_assets),
    }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _save_meta(prefix: str, result: dict, prompts: dict):
    """保存实验元数据和 prompt 到文件。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    meta_path = OUTPUT_DIR / f"{prefix}_meta.json"
    meta = {k: v for k, v in result.items() if k != "prompts"}
    meta["timestamp"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if prompts:
        prompt_path = OUTPUT_DIR / f"{prefix}_prompts.json"
        prompt_path.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_codex_review_manifest(results: list[dict], batch_ts: str) -> Path:
    """生成 Codex 评审清单 JSON — V7 升级版含 SSS 评分。"""
    manifest = {
        "harness_version": "v7_dual_track_sss",
        "batch_timestamp": batch_ts,
        "total_cases": len(results),
        "succeeded": len([r for r in results if r["status"].startswith("ok")]),
        "failed": len([r for r in results if r["status"].startswith("failed")]),
        "sss_pass_count": len([
            r for r in results
            if r.get("scoring", {}).get("commercial_pass")
        ]),
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
            "mode": r.get("mode", ""),
            "status": r["status"],
            "total_elapsed": r.get("total_elapsed", 0),
            "cost_estimate": r.get("cost_estimate", ""),
            "scoring": r.get("scoring", {}),
            "asset_count": r.get("asset_count", 0),
            "visible_count": r.get("visible_count", 0),
        }
        # 添加资产路径（用于 Codex 审片）
        if "assets" in r:
            case_entry["asset_paths"] = [a["path"] for a in r["assets"]]
        elif "final_image" in r:
            case_entry["asset_paths"] = [r["final_image"]]
        manifest["cases"].append(case_entry)

    # 维度统计
    manifest["dimension_stats"] = {
        "by_package": _group_stats(results, "package"),
        "by_framing": _group_stats(results, "framing"),
        "by_gender": _group_stats(results, "gender"),
        "by_lighting": _group_stats(results, "lighting"),
    }

    # SSS 统计
    sss_results = [r for r in results if "scoring" in r]
    if sss_results:
        manifest["sss_stats"] = {
            "identity_pass_rate": sum(1 for r in sss_results if r["scoring"].get("identity_verifiability")) / len(sss_results),
            "proportion_pass_rate": sum(1 for r in sss_results if r["scoring"].get("proportion_verifiability")) / len(sss_results),
            "hero_track_success_rate": sum(1 for r in sss_results if r["scoring"].get("hero_track_ok")) / len(sss_results),
            "avg_hero_quality": sum(r["scoring"].get("hero_quality", 0) for r in sss_results) / len(sss_results),
            "avg_delivery_quality": sum(r["scoring"].get("delivery_quality", 0) for r in sss_results) / len(sss_results),
            "commercial_pass_rate": sum(1 for r in sss_results if r["scoring"].get("commercial_pass")) / len(sss_results),
        }

    manifest_path = OUTPUT_DIR / f"v7_batch_{batch_ts}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def _group_stats(results: list[dict], key: str) -> dict:
    groups: dict[str, dict] = {}
    for r in results:
        val = r.get(key, "unknown")
        if val not in groups:
            groups[val] = {"total": 0, "ok": 0, "failed": 0, "sss_pass": 0}
        groups[val]["total"] += 1
        if r["status"].startswith("ok"):
            groups[val]["ok"] += 1
        elif r["status"].startswith("failed"):
            groups[val]["failed"] += 1
        if r.get("scoring", {}).get("commercial_pass"):
            groups[val]["sss_pass"] += 1
    return groups


# ---------------------------------------------------------------------------
# 批跑入口
# ---------------------------------------------------------------------------

async def run_batch(cases: list[dict], *, dry_run: bool = False, editorial_only: bool = False) -> list[dict]:
    """顺序执行一批测试 case。"""
    results = []
    for i, entry in enumerate(cases):
        cid = _case_id(entry)
        print(f"\n{'#'*60}")
        print(f"# [{i+1}/{len(cases)}] {cid}")
        print(f"{'#'*60}")

        try:
            result = await run_case(entry, dry_run=dry_run, editorial_only=editorial_only)
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

        if not dry_run and i < len(cases) - 1:
            print(f"  等待 3s 再跑下一个...")
            await asyncio.sleep(3)

    return results


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="V7 双轨 Harness — SSS 出片验证")
    parser.add_argument("--package", help="只跑指定套餐")
    parser.add_argument("--framing", help="只跑指定构图 (close/medium/wide)")
    parser.add_argument("--gender", help="只跑指定性别 (couple/female/male)")
    parser.add_argument("--case", help="只跑指定 case_id")
    parser.add_argument("--list", action="store_true", help="列出所有 case 不执行")
    parser.add_argument("--dry-run", action="store_true", help="只生成 prompt 不调 API")
    parser.add_argument("--editorial-only", action="store_true", help="只跑 R1-R4，不经双轨编排")
    parser.add_argument("--quick", action="store_true", help="只跑 3 个代表性 case")
    return parser.parse_args()


def filter_cases(args) -> list[dict]:
    if args.quick:
        cases = list(QUICK_MATRIX)
    else:
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

        print(f"\n--- 维度覆盖统计 ---")
        packages = set(e["package"] for e in cases)
        framings = set(_framing_of(e) for e in cases)
        genders = set(e["gender"] for e in cases)
        print(f"  套餐 ({len(packages)}): {', '.join(sorted(packages))}")
        print(f"  构图 ({len(framings)}): {', '.join(sorted(framings))}")
        print(f"  性别 ({len(genders)}): {', '.join(sorted(genders))}")
        return

    batch_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_label = "editorial-only" if args.editorial_only else "production-orchestrator"
    print(f"V7 双轨 Harness [{mode_label}] — {len(cases)} 个 case，batch={batch_ts}")
    if args.dry_run:
        print("*** DRY RUN 模式 — 只生成 prompt，不调 API ***")

    results = await run_batch(cases, dry_run=args.dry_run, editorial_only=args.editorial_only)

    manifest_path = _build_codex_review_manifest(results, batch_ts)

    # 汇总
    ok = len([r for r in results if r["status"].startswith("ok")])
    failed = len([r for r in results if r["status"].startswith("failed")])
    sss_pass = len([r for r in results if r.get("scoring", {}).get("commercial_pass")])
    hero_ok = len([r for r in results if r.get("scoring", {}).get("hero_track_ok")])
    total_time = sum(r.get("total_elapsed", 0) for r in results)
    total_cost = sum(
        float(r.get("cost_estimate", "~$0").replace("~$", ""))
        for r in results if r.get("cost_estimate")
    )

    print(f"\n{'='*60}")
    print(f"V7 批跑完成 [{mode_label}]")
    print(f"  成功: {ok}/{len(results)}")
    print(f"  失败: {failed}/{len(results)}")
    if not args.editorial_only and not args.dry_run:
        print(f"  SSS 商业通过: {sss_pass}/{ok} ({sss_pass/max(ok,1)*100:.0f}%)")
        print(f"  Hero Track 成功: {hero_ok}/{ok} ({hero_ok/max(ok,1)*100:.0f}%)")
    print(f"  总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  总成本: ~${total_cost:.2f}")
    print(f"  评审清单: {manifest_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
