"""VLM 质检服务 — 基于上下文工程的 hard/soft fail 双层判定。

Phase 2 升级：
- 质检 prompt 加入创意意图（brief_summary）
- 输出结构拆为 hard_fail + identity_match + brief_alignment + aesthetic_score
- 决策逻辑委托给 context/thresholds.py
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from io import BytesIO

import httpx
from PIL import Image

from config import settings
from models.schemas import IssueCategory, QualityIssue, RenderTrack, VerifiabilityAssessment

logger = logging.getLogger(__name__)

_UNAVAILABLE_CHANNEL_MARKERS = (
    "无可用渠道",
    "no available channel",
)


def _load_first_json_object(raw: str) -> dict:
    """Best-effort parse of the first JSON object from model output."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
        if content.lower().startswith("json"):
            content = content[4:].lstrip()

    candidates: list[str] = [content]
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        candidates.append(content[start : end + 1])

    decoder = json.JSONDecoder()
    last_error: Exception | None = None
    for candidate in candidates:
        normalized = (
            candidate.strip()
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        if not normalized:
            continue
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            last_error = exc

        try:
            json_start = normalized.find("{")
            if json_start >= 0:
                parsed, _ = decoder.raw_decode(normalized[json_start:])
                if isinstance(parsed, dict):
                    return parsed
        except json.JSONDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("No JSON object found", raw, 0)


@dataclass
class QualityReport:
    """图片质检结果 — Phase 2 升级版。"""

    passed: bool = True
    score: float = 1.0  # 向后兼容，= avg(identity, alignment, aesthetic)

    # Phase 2 新增：三维评分
    hard_fail: bool = False
    identity_match: float = 0.85
    brief_alignment: float = 0.85
    aesthetic_score: float = 0.85
    inspection_unavailable: bool = False

    issues: list[QualityIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # 修复建议（由 VLM 直接给出）
    repair_hints: list[str] = field(default_factory=list)
    verifiability: VerifiabilityAssessment = field(default_factory=VerifiabilityAssessment)

    @property
    def physical_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.category == IssueCategory.physical]

    @property
    def emotional_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.category == IssueCategory.emotional]

    @property
    def issue_descriptions(self) -> list[str]:
        return [i.description for i in self.issues]


# ---------------------------------------------------------------------------
# 质检 System Prompt — 加入创意意图对照
# ---------------------------------------------------------------------------

_CHECKER_SYSTEM_PROMPT = """\
You are a demanding wedding photography director reviewing an AI-generated image.

You evaluate THREE dimensions independently:

1. **identity_match** (0.0-1.0): The first image is the generated result. Any later images are \
reference photos of the real person or couple. Does the generated image look like the same \
person or couple? Score facial similarity, skin tone, and body proportions. If no reference \
photos are provided after the generated image, score 0.85 by default.

2. **brief_alignment** (0.0-1.0): Does the image match the creative intent? \
Is the scene, mood, wardrobe, and overall narrative consistent with what was requested?

3. **aesthetic_score** (0.0-1.0): Is it a beautiful, professional wedding photo? \
Consider composition, lighting, color harmony, and emotional impact.

Also check for **hard failures** — issues that MUST be fixed before delivery:
- Extra or missing fingers/limbs
- Body parts clipping through clothing or objects
- Severely distorted facial structure
- Major background artifacts (text, watermarks, impossible objects)
- Person is blurry or unrecognizable
- In a couple portrait, either partner's face is too hidden, too profile-heavy, or too occluded to verify identity
- One or both subjects have only one eye visible because of angle, hair, hands, or the other person's face
- Gaze direction is incoherent for the intended emotional beat, making the relationship read as awkward or staged
- Environmental color cast pushes facial skin tones far away from natural, believable skin

Couple-specific scoring guidance:
- If one partner is shown in a hard side profile and likeness cannot be verified, identity_match must drop sharply.
- If the crop is too tight to verify relative height/build against couple references, mention that limitation explicitly in issues.
- Do not reward atmosphere if the image hides the very facial landmarks needed to prove likeness.

Respond ONLY with this JSON (no markdown, no explanation):
{
  "hard_fail": true/false,
  "identity_match": 0.0-1.0,
  "brief_alignment": 0.0-1.0,
  "aesthetic_score": 0.0-1.0,
  "verifiability": {
    "is_identity_verifiable": true/false,
    "is_proportion_verifiable": true/false,
    "face_area_ratio_bride": 0.0-1.0,
    "face_area_ratio_groom": 0.0-1.0,
    "body_visibility_score": 0.0-1.0,
    "notes": ["short reason 1", "short reason 2"]
  },
  "issues": [
    {"description": "...", "category": "physical" or "emotional", "severity": 0.0-1.0, "blocking": true/false}
  ],
  "repair_hints": ["specific fix instruction 1", "specific fix instruction 2"]
}\
"""


class VLMCheckerService:
    """VLM 质检服务 — 三维评分 + hard/soft fail。"""

    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/chat/completions"
        self.model = settings.vlm_model
        self._channel_available = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.chat_api_key}",
            "Content-Type": "application/json",
        }

    def _check_api_key(self) -> None:
        if not settings.chat_api_key:
            raise RuntimeError("chat api key is not configured. Set LAOZHANG_API_KEY.")

    @staticmethod
    def _prepare_image_for_request(
        image_data: bytes,
        mime_type: str,
    ) -> tuple[bytes, str, tuple[int, int] | None, tuple[int, int] | None]:
        """压缩并缩放质检图，减少 VLM payload 和尾延迟。"""
        try:
            with Image.open(BytesIO(image_data)) as image:
                original_size = image.size
                image.load()

                if image.mode in ("RGBA", "LA") or (
                    image.mode == "P" and "transparency" in image.info
                ):
                    base = Image.new("RGB", image.size, (255, 255, 255))
                    alpha = image.convert("RGBA")
                    base.paste(alpha, mask=alpha.getchannel("A"))
                    image = base
                elif image.mode != "RGB":
                    image = image.convert("RGB")

                max_dim = max(settings.vlm_max_image_dimension, 512)
                if image.width > max_dim or image.height > max_dim:
                    image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                prepared_size = image.size
                buffer = BytesIO()
                image.save(
                    buffer,
                    format="JPEG",
                    quality=settings.vlm_jpeg_quality,
                    optimize=True,
                )
                return buffer.getvalue(), "image/jpeg", original_size, prepared_size
        except Exception:
            logger.warning("Failed to preprocess image for VLM; using original payload", exc_info=True)
            return image_data, mime_type, None, None

    async def check_image(
        self,
        image_data: bytes,
        brief_summary: str = "",
        original_prompt: str = "",
        mime_type: str = "image/png",
        reference_images: list[tuple[bytes, str]] | None = None,
        track: RenderTrack = RenderTrack.hero,
        validation_anchor: VerifiabilityAssessment | None = None,
        gender: str = "couple",
    ) -> QualityReport:
        """对一张图片执行质检，可选传入创意意图摘要。"""
        self._check_api_key()

        if not self._channel_available:
            return self._fallback_report("Quality check model channel unavailable")

        prepared_image_data, prepared_mime_type, original_size, prepared_size = (
            self._prepare_image_for_request(image_data, mime_type)
        )
        if original_size and prepared_size:
            logger.info(
                "VLM image prepared: %s bytes %s -> %s bytes %s",
                len(image_data),
                original_size,
                len(prepared_image_data),
                prepared_size,
            )

        b64_image = base64.b64encode(prepared_image_data).decode()
        data_uri = f"data:{prepared_mime_type};base64,{b64_image}"

        # 用户消息：图片 + 创意意图（如果有）
        user_parts: list[dict] = [
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]
        if reference_images:
            for ref_data, ref_mime in reference_images:
                prepared_ref, prepared_ref_mime, _, _ = self._prepare_image_for_request(ref_data, ref_mime)
                user_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{prepared_ref_mime};base64,{base64.b64encode(prepared_ref).decode()}",
                        },
                    }
                )
        user_text = "Review this AI-generated wedding photo."
        if brief_summary:
            user_text += f"\n\nCreative intent: {brief_summary}"
        if original_prompt:
            user_text += f"\n\nOriginal render instructions to preserve: {original_prompt}"
        if reference_images:
            user_text += (
                "\n\nImage order: image 1 is the generated result. Later images are the identity "
                "references that must be matched."
            )
        is_solo = gender in ("female", "male")
        if track == RenderTrack.validation:
            if is_solo:
                role = "bride" if gender == "female" else "groom"
                face_key = "face_area_ratio_bride" if gender == "female" else "face_area_ratio_groom"
                user_text += (
                    f"\n\nTrack goal: this is a VALIDATION-track render for commercial identity verification of a SOLO {role} portrait. "
                    "Apply STRICT standards:\n"
                    f"- face_area_ratio = approximate fraction of total image area occupied by the {role}'s face\n"
                    "- A face that is a tiny dot scores ~0.01; a well-framed medium portrait scores ~0.08-0.15\n"
                    f"- is_identity_verifiable = true ONLY if the {role}'s face is frontal/open-3/4 with both eyes clearly visible "
                    "AND face area is large enough to compare against reference photos\n"
                    "- is_proportion_verifiable = true ONLY if you can see enough body (at least waist-up) to verify head-body ratio\n"
                    "- body_visibility_score: 1.0 = full body; 0.7 = waist-up; 0.5 = chest-up; 0.3 = face only\n"
                    f"- Set the OTHER person's face_area_ratio to 0.0 (this is a solo portrait, only score the {role})\n"
                    "Be conservative — when in doubt, fail the verification."
                )
            else:
                user_text += (
                    "\n\nTrack goal: this is a VALIDATION-track render for commercial identity verification of a COUPLE. "
                    "Apply STRICT standards:\n"
                    "- face_area_ratio = approximate fraction of total image area occupied by each face\n"
                    "- A face that is a tiny dot in a landscape scores ~0.01; a well-framed medium portrait scores ~0.08-0.15\n"
                    "- is_identity_verifiable = true ONLY if BOTH faces are frontal/open-3/4 with both eyes clearly visible "
                    "AND face area is large enough to compare against reference photos\n"
                    "- is_proportion_verifiable = true ONLY if you can clearly determine relative height, head-body ratio, "
                    "and shoulder line between BOTH partners\n"
                    "- body_visibility_score: 1.0 = full body from head to toe; 0.7 = waist-up; 0.5 = chest-up; 0.3 = face only\n"
                    "- If heavy backlighting silhouettes a face, set is_identity_verifiable to false\n"
                    "- If one face is in profile or partially hidden, set that person's face_area_ratio to 0.0\n"
                    "Be conservative — when in doubt, fail the verification rather than pass it."
                )
        elif track == RenderTrack.hero:
            user_text += (
                "\n\nTrack goal: this is a hero-track render. Atmosphere and visual impact matter, "
                "but identity must still be assessable. If a face is too small (< 2.5% of image area), "
                "in hard profile, or hidden by shadow/backlighting, set is_identity_verifiable to false. "
                "A beautiful photo that cannot prove it depicts the real person has limited commercial value."
            )
            if validation_anchor is not None:
                user_text += (
                    "\n\nValidation-track anchor already passed with: "
                    f"identity_verifiable={validation_anchor.is_identity_verifiable}, "
                    f"proportion_verifiable={validation_anchor.is_proportion_verifiable}, "
                    f"body_visibility_score={validation_anchor.body_visibility_score:.2f}. "
                    "The hero render must not contradict those proven constraints."
                )
        else:
            user_text += (
                "\n\nTrack goal: this is the ONLY formal V14 delivery render. "
                "Judge it as a commercially deliverable wedding photo, not as an experiment. "
                "Identity, body proportion, wardrobe credibility, and premium atmosphere must all hold together. "
                "If the image is beautiful but the real people are not verifiable, fail it."
            )
        user_parts.append({"type": "text", "text": user_text})

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _CHECKER_SYSTEM_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": settings.vlm_max_tokens,
            "temperature": 0.1,
        }

        try:
            started_at = time.perf_counter()
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.vlm_timeout_seconds)) as client:
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            logger.info(
                "VLM quality check succeeded in %.1fs for model %s",
                time.perf_counter() - started_at,
                self.model,
            )

            content = data["choices"][0]["message"]["content"]
            return self._parse_report(content)

        except httpx.HTTPStatusError as exc:
            self._maybe_disable_channel(exc.response)
            logger.exception("VLM quality check failed")
            return self._fallback_report("Quality check service unavailable")
        except httpx.TimeoutException:
            logger.exception(
                "VLM quality check timed out after %ss for model %s",
                settings.vlm_timeout_seconds,
                self.model,
            )
            return self._fallback_report("Quality check service unavailable")
        except Exception:
            logger.exception("VLM quality check failed")
            return self._fallback_report("Quality check service unavailable")

    def _parse_report(self, raw_content: str) -> QualityReport:
        """解析 VLM 返回的 JSON 质检报告。"""
        try:
            result = _load_first_json_object(raw_content)

            hard_fail = bool(result.get("hard_fail", False))
            identity = float(result.get("identity_match", 0.85))
            alignment = float(result.get("brief_alignment", 0.85))
            aesthetic = float(result.get("aesthetic_score", 0.85))

            # 向后兼容 score 字段
            score = (identity + alignment + aesthetic) / 3

            # 解析 issues
            raw_issues = result.get("issues", [])
            issues: list[QualityIssue] = []
            for item in raw_issues:
                if isinstance(item, dict):
                    cat_str = item.get("category", "physical")
                    try:
                        cat = IssueCategory(cat_str)
                    except ValueError:
                        cat = IssueCategory.physical
                    issues.append(QualityIssue(
                        description=item.get("description", str(item)),
                        category=cat,
                        severity=float(item.get("severity", 0.5)),
                    ))
                elif isinstance(item, str):
                    issues.append(QualityIssue(
                        description=item,
                        category=self._guess_category(item),
                        severity=0.5,
                    ))

            repair_hints = result.get("repair_hints", [])
            if isinstance(repair_hints, str):
                repair_hints = [repair_hints]

            raw_verifiability = result.get("verifiability")
            if not isinstance(raw_verifiability, dict):
                raw_verifiability = {
                    "is_identity_verifiable": result.get("is_identity_verifiable", False),
                    "is_proportion_verifiable": result.get("is_proportion_verifiable", False),
                    "face_area_ratio_bride": result.get("face_area_ratio_bride", 0.0),
                    "face_area_ratio_groom": result.get("face_area_ratio_groom", 0.0),
                    "body_visibility_score": result.get("body_visibility_score", 0.0),
                    "notes": result.get("verifiability_notes", []),
                }
            notes = raw_verifiability.get("notes", [])
            if isinstance(notes, str):
                notes = [notes]
            verifiability = VerifiabilityAssessment(
                is_identity_verifiable=bool(raw_verifiability.get("is_identity_verifiable", False)),
                is_proportion_verifiable=bool(raw_verifiability.get("is_proportion_verifiable", False)),
                face_area_ratio_bride=float(raw_verifiability.get("face_area_ratio_bride", 0.0) or 0.0),
                face_area_ratio_groom=float(raw_verifiability.get("face_area_ratio_groom", 0.0) or 0.0),
                body_visibility_score=float(raw_verifiability.get("body_visibility_score", 0.0) or 0.0),
                notes=list(notes),
            )

            passed = not hard_fail and score >= 0.80

            return QualityReport(
                passed=passed,
                score=score,
                hard_fail=hard_fail,
                identity_match=identity,
                brief_alignment=alignment,
                aesthetic_score=aesthetic,
                issues=issues,
                suggestions=result.get("suggestions", []),
                repair_hints=repair_hints,
                verifiability=verifiability,
            )
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse VLM report, raw: %s", raw_content[:200])
            # 尝试从截断的 JSON 中提取关键字段（max_tokens 不足时常见）
            return self._rescue_truncated_report(raw_content)

    def _rescue_truncated_report(self, raw: str) -> QualityReport:
        """从被截断的 JSON 中尽力提取关键数值字段。"""
        import re

        def _extract_float(key: str, default: float = 0.0) -> float:
            m = re.search(rf'"{key}"\s*:\s*([0-9]+\.?[0-9]*)', raw)
            return float(m.group(1)) if m else default

        def _extract_bool(key: str, default: bool = False) -> bool:
            m = re.search(rf'"{key}"\s*:\s*(true|false)', raw, re.IGNORECASE)
            return m.group(1).lower() == "true" if m else default

        identity = _extract_float("identity_match", 0.0)
        alignment = _extract_float("brief_alignment", 0.0)
        aesthetic = _extract_float("aesthetic_score", 0.0)
        hard_fail = _extract_bool("hard_fail", False)

        # 至少需要提取到 identity_match 才算有效
        if identity == 0.0 and alignment == 0.0 and aesthetic == 0.0:
            logger.warning("Truncated JSON rescue failed: no scores found")
            return self._fallback_report("Quality report parsing failed")

        verifiability = VerifiabilityAssessment(
            is_identity_verifiable=_extract_bool("is_identity_verifiable", False),
            is_proportion_verifiable=_extract_bool("is_proportion_verifiable", False),
            face_area_ratio_bride=_extract_float("face_area_ratio_bride", 0.0),
            face_area_ratio_groom=_extract_float("face_area_ratio_groom", 0.0),
            body_visibility_score=_extract_float("body_visibility_score", 0.0),
            notes=["rescued from truncated VLM response"],
        )

        score = (identity + alignment + aesthetic) / 3
        passed = not hard_fail and score >= 0.80
        logger.info(
            "Rescued truncated VLM report: id=%.2f align=%.2f aes=%.2f hard_fail=%s",
            identity, alignment, aesthetic, hard_fail,
        )
        return QualityReport(
            passed=passed,
            score=score,
            hard_fail=hard_fail,
            identity_match=identity,
            brief_alignment=alignment,
            aesthetic_score=aesthetic,
            issues=[],
            suggestions=[],
            repair_hints=[],
            verifiability=verifiability,
        )

    @staticmethod
    def _guess_category(description: str) -> IssueCategory:
        emotional_keywords = [
            "expression", "emotion", "eye", "gaze", "smile", "mood",
            "表情", "情绪", "眼神", "笑", "氛围", "僵硬",
        ]
        desc_lower = description.lower()
        for kw in emotional_keywords:
            if kw in desc_lower:
                return IssueCategory.emotional
        return IssueCategory.physical

    def _maybe_disable_channel(self, response: httpx.Response) -> None:
        try:
            data = response.json()
        except ValueError:
            return
        message = str(data.get("error", {}).get("message", "")).lower()
        if any(marker in message for marker in _UNAVAILABLE_CHANNEL_MARKERS):
            self._channel_available = False
            logger.warning(
                "VLM model channel unavailable for model %s; "
                "future requests will use local fallback.",
                self.model,
            )

    @staticmethod
    def _fallback_report(reason: str) -> QualityReport:
        """质检不可用时显式阻断交付，避免静默放行。"""
        return QualityReport(
            passed=False,
            score=0.0,
            hard_fail=False,
            identity_match=0.0,
            brief_alignment=0.0,
            aesthetic_score=0.0,
            inspection_unavailable=True,
            verifiability=VerifiabilityAssessment(),
            issues=[QualityIssue(
                description=reason,
                category=IssueCategory.physical,
                severity=1.0,
            )],
            suggestions=["Manual review recommended"],
        )

    async def check_and_suggest_fix_prompt(
        self,
        image_data: bytes,
        original_prompt: str,
        brief_summary: str = "",
        mime_type: str = "image/png",
        reference_images: list[tuple[bytes, str]] | None = None,
        track: RenderTrack = RenderTrack.hero,
        validation_anchor: VerifiabilityAssessment | None = None,
        gender: str = "couple",
    ) -> tuple[QualityReport, str | None]:
        """质检 + 修复 prompt。brief_summary 用于对照创意意图审片。"""
        report = await self.check_image(
            image_data,
            brief_summary,
            original_prompt,
            mime_type,
            reference_images,
            track,
            validation_anchor,
            gender,
        )

        if report.inspection_unavailable:
            return report, None

        if report.passed:
            return report, None

        # 优先用 VLM 给出的 repair_hints
        if report.repair_hints:
            fix_text = "; ".join(report.repair_hints)
        else:
            fix_text = "; ".join(i.description for i in report.issues)

        fix_prompt = (
            f"Fix these issues: {fix_text}. "
            f"Preserve the facial identity, composition, and overall style. "
            f"Ensure correct anatomy and natural expressions."
        )
        return report, fix_prompt


vlm_checker_service = VLMCheckerService()
