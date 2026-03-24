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
from dataclasses import dataclass, field

import httpx

from config import settings
from models.schemas import IssueCategory, QualityIssue

logger = logging.getLogger(__name__)

_UNAVAILABLE_CHANNEL_MARKERS = (
    "无可用渠道",
    "no available channel",
)


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

1. **identity_match** (0.0-1.0): Does the person in the generated image look like \
the same person from the reference photos? Score facial similarity, skin tone, \
body proportions. If no reference was provided, score 0.85 by default.

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

Respond ONLY with this JSON (no markdown, no explanation):
{
  "hard_fail": true/false,
  "identity_match": 0.0-1.0,
  "brief_alignment": 0.0-1.0,
  "aesthetic_score": 0.0-1.0,
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

    async def check_image(
        self,
        image_data: bytes,
        brief_summary: str = "",
        mime_type: str = "image/png",
    ) -> QualityReport:
        """对一张图片执行质检，可选传入创意意图摘要。"""
        self._check_api_key()

        if not self._channel_available:
            return self._fallback_report("Quality check model channel unavailable")

        b64_image = base64.b64encode(image_data).decode()
        data_uri = f"data:{mime_type};base64,{b64_image}"

        # 用户消息：图片 + 创意意图（如果有）
        user_parts: list[dict] = [
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]
        user_text = "Review this AI-generated wedding photo."
        if brief_summary:
            user_text += f"\n\nCreative intent: {brief_summary}"
        user_parts.append({"type": "text", "text": user_text})

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _CHECKER_SYSTEM_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            return self._parse_report(content)

        except httpx.HTTPStatusError as exc:
            self._maybe_disable_channel(exc.response)
            logger.exception("VLM quality check failed")
            return self._fallback_report("Quality check service unavailable")
        except Exception:
            logger.exception("VLM quality check failed")
            return self._fallback_report("Quality check service unavailable")

    def _parse_report(self, raw_content: str) -> QualityReport:
        """解析 VLM 返回的 JSON 质检报告。"""
        content = raw_content.strip()

        # 去掉 markdown 代码块
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.strip().startswith("```") and not inside:
                    inside = True
                    continue
                if line.strip() == "```" and inside:
                    break
                if inside:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        try:
            result = json.loads(content)

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
            )
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse VLM report, raw: %s", raw_content[:200])
            return self._fallback_report("Quality report parsing failed")

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
    ) -> tuple[QualityReport, str | None]:
        """质检 + 修复 prompt。brief_summary 用于对照创意意图审片。"""
        report = await self.check_image(image_data, brief_summary, mime_type)

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
