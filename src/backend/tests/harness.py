"""三轮迭代生图质量 Harness。

已验证最优策略：
  R1: text_to_image — 纯文本场景底图（不传参考图，不扛身份压力）
  R2: image_to_image — 基于 R1 精修服饰/动作/手势
  R3: multi_reference_generate — 生成语义 prompt，R2 构图 + 身份参考图

每个实验配置可调整三轮各自的 prompt 策略，追踪效果差异。
"""

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
    SYSTEM_IDENTITY_PHOTOGRAPHER,
    COUPLE_BODY_PROPORTION_ANCHOR,
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
USER_ID = "c93348267c8b"  # 5 张参考图的测试用户

# ---------------------------------------------------------------------------
# R3 身份注入 prompt 模板（核心资产，实验验证过的生成语义）
# ---------------------------------------------------------------------------

R3_IDENTITY_FUSION_PROMPT = """You are a world-class wedding photographer creating the final editorial image.

Generate a new image that combines the SCENE COMPOSITION from the first reference image and the FACIAL IDENTITY from the remaining reference images.

The first reference image provides the exact scene composition, camera angle, lighting, wardrobe, pose, and background. Reproduce this scene faithfully.

The remaining reference images show the real couple. Their facial identity MUST appear in the final image:
- Identical eye shape, nose bridge contour, jawline angle, lip proportions, skin tone
- Natural hair texture and style consistent with the references
- Body proportions and build faithful to the reference photos

{brief_context}

{variant_context}

CRITICAL RULES:
- The scene comes from image 1. The faces come from the remaining images.
- Do NOT average or blend faces. Each person must look exactly like their reference.
- Preserve the exact lighting, color grade, and photographic quality of the scene.
- This must look like a real high-end editorial wedding photograph, not AI-generated.

{avoid_context}"""

# ---------------------------------------------------------------------------
# 实验配置
# ---------------------------------------------------------------------------

class ExperimentConfig:
    """一组三轮实验的完整配置。"""

    def __init__(
        self,
        name: str,
        description: str,
        package_id: str = "iceland",
        variant_index: int = 0,
        makeup_style: str = "natural",
        gender: str = "couple",
        # R1 覆盖
        r1_prompt_override: str | None = None,
        # R2 覆盖
        r2_prompt_override: str | None = None,
        r2_hints: list[str] | None = None,
        # R3 覆盖
        r3_prompt_override: str | None = None,
        r3_extra_identity_cues: str = "",
        # Brief 字段覆盖
        brief_overrides: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.package_id = package_id
        self.variant_index = variant_index
        self.makeup_style = makeup_style
        self.gender = gender
        self.r1_prompt_override = r1_prompt_override
        self.r2_prompt_override = r2_prompt_override
        self.r2_hints = r2_hints or [
            "Refine the wardrobe details: fabric texture, draping, and fit",
            "Improve hand placement and gesture naturalness",
            "Enhance the interaction between the couple — make it feel genuine",
        ]
        self.r3_prompt_override = r3_prompt_override
        self.r3_extra_identity_cues = r3_extra_identity_cues
        self.brief_overrides = brief_overrides or {}


# ---------------------------------------------------------------------------
# 三轮生图核心
# ---------------------------------------------------------------------------

async def run_three_rounds(config: ExperimentConfig) -> dict:
    """执行三轮迭代生图。"""

    upload_dir = UPLOAD_DIR / USER_ID
    if not upload_dir.exists():
        raise RuntimeError(f"Upload dir not found: {upload_dir}")

    # 准备参考图
    ref_set = select_references(upload_dir)
    print(f"  参考图: {ref_set.count} 张 "
          f"(roles={ref_set.selected_role_counts}, "
          f"couple_anchor={ref_set.has_couple_anchor})")

    if not ref_set.has_identity:
        raise RuntimeError("没有身份参考图，无法执行三轮法")

    # 构建 brief
    brief = get_brief(config.package_id)
    for key, val in config.brief_overrides.items():
        if hasattr(brief, key):
            setattr(brief, key, val)

    slots = render_slots(makeup_style=config.makeup_style, gender=config.gender)
    variants = get_variants(brief, count=max(config.variant_index + 1, 1))
    variant = variants[config.variant_index % len(variants)]

    # 输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{config.name}_{ts}"

    results = {"rounds": [], "config": config.name}
    total_cost_estimate = 0.0

    # =========================================================
    # Round 1: text_to_image — 纯场景底图
    # =========================================================
    print(f"\n  --- Round 1: 场景底图 (text_to_image, 无参考图) ---")

    if config.r1_prompt_override:
        r1_prompt = config.r1_prompt_override
    else:
        # 用标准 prompt 但标记无参考图
        r1_prompt = assemble_generation_prompt(
            brief=brief,
            variant=variant,
            slots=slots,
            has_refs=False,  # 不传参考图
            has_couple_refs=False,
            has_couple_anchor=False,
        )

    print(f"  R1 prompt ({len(r1_prompt)} chars): {r1_prompt[:200]}...")

    t0 = time.time()
    try:
        r1_img = await nano_banana_service.text_to_image(prompt=r1_prompt)
        r1_time = time.time() - t0
        r1_path = OUTPUT_DIR / f"{prefix}_R1_scene.png"
        r1_path.write_bytes(r1_img)
        print(f"  R1 OK: {len(r1_img)} bytes, {r1_time:.1f}s → {r1_path.name}")
        results["rounds"].append({
            "round": 1, "status": "ok", "bytes": len(r1_img),
            "elapsed": round(r1_time, 1), "path": str(r1_path),
        })
        total_cost_estimate += 0.13
    except Exception as e:
        print(f"  R1 FAILED: {e}")
        return {"status": "failed_r1", "error": str(e)}

    # =========================================================
    # Round 2: image_to_image — 服饰/动作精修
    # =========================================================
    print(f"\n  --- Round 2: 服饰精修 (image_to_image) ---")

    if config.r2_prompt_override:
        r2_prompt = config.r2_prompt_override
    else:
        r2_hints_text = "\n".join(f"- {h}" for h in config.r2_hints)
        r2_prompt = (
            f"{SYSTEM_IDENTITY_PHOTOGRAPHER}\n\n"
            f"Refine this wedding photograph. Keep the scene composition, lighting, "
            f"and camera angle exactly as they are. Focus on these improvements:\n"
            f"{r2_hints_text}\n\n"
            f"Original creative intent: {brief.story} {brief.visual_essence}\n"
            f"Wardrobe: {brief.wardrobe_bride} / {brief.wardrobe_groom}\n"
            f"Makeup: {slots.makeup or brief.makeup_default}\n\n"
            f"Do NOT change the faces, the background, or the overall framing. "
            f"This is a refinement pass, not a redesign."
        )

    print(f"  R2 prompt ({len(r2_prompt)} chars): {r2_prompt[:200]}...")

    t0 = time.time()
    try:
        r2_img = await nano_banana_service.image_to_image(
            prompt=r2_prompt,
            image_data=r1_img,
        )
        r2_time = time.time() - t0
        r2_path = OUTPUT_DIR / f"{prefix}_R2_refined.png"
        r2_path.write_bytes(r2_img)
        print(f"  R2 OK: {len(r2_img)} bytes, {r2_time:.1f}s → {r2_path.name}")
        results["rounds"].append({
            "round": 2, "status": "ok", "bytes": len(r2_img),
            "elapsed": round(r2_time, 1), "path": str(r2_path),
        })
        total_cost_estimate += 0.13
    except Exception as e:
        print(f"  R2 FAILED: {e}")
        return {"status": "failed_r2", "error": str(e)}

    # =========================================================
    # Round 3: multi_reference_generate — 身份注入（生成语义）
    # =========================================================
    print(f"\n  --- Round 3: 身份注入 (multi_reference_generate, 生成语义) ---")

    if config.r3_prompt_override:
        r3_prompt = config.r3_prompt_override
    else:
        brief_context = (
            f"Scene story: {brief.story}\n"
            f"Visual style: {brief.aesthetic}\n"
            f"Wardrobe — Her: {brief.wardrobe_bride} / Him: {brief.wardrobe_groom}\n"
            f"Emotion: {brief.emotion}"
        )
        variant_context = (
            f"This shot: {variant.intent}. Framing: {variant.framing}. "
            f"{variant.action}."
        )
        avoid_list = list(brief.avoid_global) + list(variant.avoid_local)
        avoid_context = f"Avoid: {', '.join(avoid_list)}." if avoid_list else ""

        r3_prompt = R3_IDENTITY_FUSION_PROMPT.format(
            brief_context=brief_context,
            variant_context=variant_context,
            avoid_context=avoid_context,
        )

        if config.r3_extra_identity_cues:
            r3_prompt += f"\n\nAdditional identity cues: {config.r3_extra_identity_cues}"

    print(f"  R3 prompt ({len(r3_prompt)} chars): {r3_prompt[:200]}...")

    # R3 的参考图排列：R2 成品图放第一张（构图参考），然后是身份参考图
    r3_refs: list[tuple[bytes, str]] = [
        (r2_img, "image/png"),  # 第一张：构图参考
    ] + ref_set.all_refs  # 后面：身份参考

    print(f"  R3 参考图: {len(r3_refs)} 张 (1=构图 + {ref_set.count}=身份)")

    t0 = time.time()
    try:
        r3_img = await nano_banana_service.multi_reference_generate(
            prompt=r3_prompt,
            reference_images=r3_refs,
        )
        r3_time = time.time() - t0
        r3_path = OUTPUT_DIR / f"{prefix}_R3_final.png"
        r3_path.write_bytes(r3_img)
        print(f"  R3 OK: {len(r3_img)} bytes, {r3_time:.1f}s → {r3_path.name}")
        results["rounds"].append({
            "round": 3, "status": "ok", "bytes": len(r3_img),
            "elapsed": round(r3_time, 1), "path": str(r3_path),
        })
        total_cost_estimate += 0.13
    except Exception as e:
        print(f"  R3 FAILED: {e}")
        return {"status": "failed_r3", "error": str(e)}

    # 汇总
    total_time = sum(r["elapsed"] for r in results["rounds"])
    results["status"] = "ok"
    results["total_elapsed"] = round(total_time, 1)
    results["cost_estimate"] = f"~${total_cost_estimate:.2f}"
    results["final_image"] = str(r3_path)

    # 保存实验元数据
    meta = {
        "experiment": config.name,
        "description": config.description,
        "package_id": config.package_id,
        "variant_id": variant.id,
        "ref_count": ref_set.count,
        "ref_roles": ref_set.selected_role_counts,
        "rounds": results["rounds"],
        "total_elapsed": results["total_elapsed"],
        "cost_estimate": results["cost_estimate"],
        "timestamp": ts,
    }
    meta_path = OUTPUT_DIR / f"{prefix}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # 保存各轮 prompt
    prompts = {"r1": r1_prompt, "r2": r2_prompt, "r3": r3_prompt}
    prompt_path = OUTPUT_DIR / f"{prefix}_prompts.json"
    prompt_path.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  总耗时: {total_time:.1f}s, 预估成本: ~${total_cost_estimate:.2f}")
    print(f"  最终成片: {r3_path}")
    print(f"  元数据: {meta_path}")

    return results


# ---------------------------------------------------------------------------
# 预定义实验配置
# ---------------------------------------------------------------------------

EXPERIMENTS = {
    "baseline": ExperimentConfig(
        name="baseline",
        description="三轮法基线：标准 prompt，iceland intimate (close-up)，不做任何额外调整",
        package_id="iceland",
        variant_index=0,  # iceland_intimate: close
    ),
    "baseline_wide": ExperimentConfig(
        name="baseline_wide",
        description="三轮法基线：wide shot (iceland_epic)，测试全身构图下的身份保持",
        package_id="iceland",
        variant_index=1,  # iceland_epic: wide
    ),
    "cyberpunk": ExperimentConfig(
        name="cyberpunk",
        description="三轮法 + cyberpunk 套餐，测试不同风格的泛化能力",
        package_id="cyberpunk",
        variant_index=0,
    ),
    "enhanced_identity": ExperimentConfig(
        name="enhanced_identity",
        description="三轮法 + 增强身份锁定：R3 prompt 增加更具体的面部特征描述",
        package_id="iceland",
        variant_index=0,
        r3_extra_identity_cues=(
            "Pay special attention to: the groom's facial hair pattern and density, "
            "the exact shape of both partners' eyes and eyebrows, "
            "the bride's cheekbone structure and face shape. "
            "These details are non-negotiable — the couple must recognize themselves."
        ),
    ),
    "v4_single_image": ExperimentConfig(
        name="v4_single_image",
        description=(
            "综合 v2(B+) + v3 教训: R1 控制裁切(85mm close-up); "
            "R2 绝不改构图只做细节精修; R3 强制单张输出 + 白纱可见 + 新娘身份锁定"
        ),
        package_id="iceland",
        variant_index=0,
        # R2: 严格限制只做细节精修，绝不改构图
        r2_hints=[
            "Refine ONLY within the existing frame — do NOT change the crop, zoom, camera distance, or composition in any way",
            "Improve wardrobe texture: ensure the white lace gown is crisp and detailed",
            "Fix hand anatomy — all fingers clearly defined with natural joints",
            "Add realistic skin texture: visible pores, natural imperfections",
            "Enhance couple interaction — make it feel genuine and emotionally intimate",
            "Do NOT recompose, reframe, zoom in, zoom out, or change the camera angle",
        ],
        r3_extra_identity_cues=(
            "OUTPUT FORMAT: Generate exactly ONE single photograph. Do NOT create a diptych, collage, split-screen, or multi-panel image.\n\n"
            "CRITICAL IDENTITY REQUIREMENTS:\n"
            "- The bride has a ROUND, SOFT face with full cheeks — do NOT slim or idealize her jawline\n"
            "- The bride has MEDIUM-LENGTH STRAIGHT BLACK HAIR, simple and natural\n"
            "- Preserve the bride's exact eye shape (slightly hooded, warm), nose width, lip fullness\n"
            "- The groom has a DEFINED BEARD and slightly angular jaw — preserve beard density exactly\n"
            "- Both partners have warm, golden-undertone Asian skin\n"
            "- Skin must show real texture: pores, subtle warmth variation, not airbrushed\n"
            "- The bride's WHITE LACE GOWN must be clearly visible — no dark shawl or wrap\n"
            "- Do NOT reinterpret the pose or camera angle — only change faces and ensure wardrobe is correct"
        ),
        brief_overrides={
            "wardrobe_bride": (
                "Flowing white lace gown catching arctic wind — "
                "the white fabric must be prominently visible from shoulders to waist, "
                "NO dark shawl, wrap, jacket, or covering"
            ),
            "avoid_global": [
                "oversaturated aurora",
                "tropical warmth",
                "stiff poses",
                "generic model faces",
                "extra fingers or limbs",
                "snow that looks like white noise",
                "airbrushed skin",
                "dark shawl or wrap covering the bride's gown",
                "idealized Western beauty standards on Asian faces",
                "face slimming or jawline reshaping",
                "wavy or curly hair on the bride",
                "diptych",
                "collage",
                "split-screen",
                "multi-panel layout",
            ],
        },
    ),
    "v3_wardrobe_fix": ExperimentConfig(
        name="v3_wardrobe_fix",
        description=(
            "基于 Codex B+ 评审: 修复白纱可见度(禁深色披肩) + 新娘发型精确锁定(中长直黑发) "
            "+ 保持 v2 的紧凑裁切和新郎身份效果"
        ),
        package_id="iceland",
        variant_index=0,
        r2_hints=[
            "Refine the wardrobe details: fabric texture, draping, and fit",
            "The bride's WHITE FLOWING GOWN must be clearly visible from shoulder to waist — remove or minimize any dark wrap, shawl, or jacket obscuring the bodice",
            "Fix hand anatomy — ensure all fingers are clearly defined with natural joints",
            "Add realistic skin texture: visible pores, subtle imperfections, natural skin grain",
            "Crop tighter: editorial close-up, 85mm portrait lens feel, shallow depth of field",
        ],
        r3_extra_identity_cues=(
            "CRITICAL IDENTITY REQUIREMENTS:\n"
            "- The bride has a ROUND, SOFT face with full cheeks — do NOT slim or idealize her jawline\n"
            "- The bride has MEDIUM-LENGTH STRAIGHT BLACK HAIR, not wavy, not curly, not long — keep it simple and natural\n"
            "- Preserve the bride's exact eye shape (slightly hooded, warm), natural nose width, and lip fullness\n"
            "- The groom has a DEFINED BEARD and slightly angular jaw — preserve beard density exactly\n"
            "- Both partners have warm, golden-undertone Asian skin\n"
            "- Skin must show real texture: pores, subtle warmth variation, not airbrushed\n"
            "- The bride's WHITE GOWN must be clearly visible — no dark shawl or wrap covering the dress\n"
            "- Do NOT reinterpret the pose or camera angle — only change faces and ensure wardrobe is correct"
        ),
        brief_overrides={
            "wardrobe_bride": (
                "Flowing white gown with long train catching arctic wind — "
                "the white fabric must be prominently visible from shoulders to waist, "
                "NO dark shawl, wrap, jacket, or covering obscuring the gown"
            ),
            "avoid_global": [
                "oversaturated aurora",
                "tropical warmth",
                "stiff poses",
                "generic model faces",
                "extra fingers or limbs",
                "snow that looks like white noise",
                "airbrushed skin",
                "dark shawl or wrap covering the bride's white gown",
                "idealized Western beauty standards on Asian faces",
                "face slimming or jawline reshaping",
                "wavy or curly hair on the bride",
            ],
        },
    ),
    "v2_codex_feedback": ExperimentConfig(
        name="v2_codex_feedback",
        description=(
            "基于 Codex B 评审反馈优化：(1) R1 要求更紧凑裁切 + 真实皮肤纹理; "
            "(2) R2 增加手部细节修复; "
            "(3) R3 强化新娘身份锁定 + 保持亚洲面部结构 + 不动姿势"
        ),
        package_id="iceland",
        variant_index=0,
        # R2: 在标准精修基础上加入真实感和手部修复
        r2_hints=[
            "Refine the wardrobe details: fabric texture, draping, and fit",
            "Fix hand anatomy — ensure all fingers are clearly defined with natural joints",
            "Add realistic skin texture: visible pores, subtle imperfections, natural skin grain",
            "Enhance the interaction between the couple — make it feel genuine and intimate",
            "Crop tighter: this should feel like an 85mm portrait lens close-up with shallow depth of field",
        ],
        # R3: 强化身份锁定，特别是新娘
        r3_extra_identity_cues=(
            "CRITICAL IDENTITY REQUIREMENTS:\n"
            "- The bride has a ROUND, SOFT face shape with full cheeks — do NOT slim or idealize her jawline\n"
            "- Preserve the bride's exact eye shape (slightly hooded, warm), nose width, and natural lip fullness\n"
            "- The groom has a DEFINED BEARD and slightly angular jaw — preserve beard density and pattern exactly\n"
            "- Both partners have warm, golden-undertone Asian skin — do NOT lighten or cool the skin tone\n"
            "- Preserve natural flyaway hair strands and wind-touched texture\n"
            "- Skin must show real texture: pores, subtle warmth variation, not airbrushed smoothness\n"
            "- Do NOT reinterpret the pose, body position, or camera angle from the scene reference\n"
            "- Only change the faces — everything else stays exactly as it is in image 1"
        ),
        brief_overrides={
            # 强化 avoid，减少 AI 光滑感
            "avoid_global": [
                "oversaturated aurora",
                "tropical warmth",
                "stiff poses",
                "generic model faces",
                "extra fingers or limbs",
                "snow that looks like white noise",
                "airbrushed skin",
                "plastic-looking texture",
                "idealized Western beauty standards on Asian faces",
                "face slimming or jawline reshaping",
            ],
        },
    ),
}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    config = EXPERIMENTS.get(name)
    if not config:
        print(f"可用实验: {', '.join(EXPERIMENTS.keys())}")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"实验: {config.name}")
    print(f"描述: {config.description}")
    print(f"{'='*60}")

    result = await run_three_rounds(config)
    print(f"\n{'='*60}")
    print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
