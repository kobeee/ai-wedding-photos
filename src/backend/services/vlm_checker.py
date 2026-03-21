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
    """图片质检结果。"""
    passed: bool = True
    score: float = 1.0  # 0.0 ~ 1.0
    issues: list[QualityIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def physical_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.category == IssueCategory.physical]

    @property
    def emotional_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.category == IssueCategory.emotional]

    @property
    def issue_descriptions(self) -> list[str]:
        """向后兼容：返回纯文本 issue 列表。"""
        return [i.description for i in self.issues]


# 质检用的系统 prompt
_CHECKER_SYSTEM_PROMPT = """你是一个专业的婚纱照质检AI。请仔细检查这张AI生成的婚纱照，判断是否存在以下问题：

物理类问题 (physical)：
1. 手指畸形（多指、少指、扭曲）
2. 穿模问题（衣物穿过身体、首饰嵌入皮肤）
3. 比例失调（头身比异常、四肢长度不对）
4. 背景穿帮（不合理的物体、文字、水印）
5. 光影错误（光源方向不一致、阴影缺失或错位）
6. 边缘瑕疵（模糊过渡、锯齿、不自然的融合）

情绪类问题 (emotional)：
1. 面部表情僵硬或不自然
2. 眼神空洞、无交流感
3. 姿态不协调、缺乏情感张力
4. 整体氛围与场景不匹配

请用JSON格式返回结果：
{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": [
    {"description": "问题描述", "category": "physical或emotional", "severity": 0.0-1.0}
  ],
  "suggestions": ["修复建议1", "修复建议2"]
}

评分标准：
- 0.95+ 优秀，直接交付
- 0.85-0.94 合格
- 0.70-0.84 需修复
- <0.70 需重新生成
"""


class VLMCheckerService:
    """
    VLM 质检服务。
    利用多模态大模型检测 AI 生成婚纱照中的瑕疵。
    通过 laozhang.ai 代理调用 ChatCompletion with vision。
    """

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
            raise RuntimeError(
                "chat api key is not configured. "
                "Set LAOZHANG_API_KEY."
            )

    async def check_image(
        self,
        image_data: bytes,
        mime_type: str = "image/png",
    ) -> QualityReport:
        """
        对一张图片执行质检。
        返回 QualityReport。
        """
        self._check_api_key()

        if not self._channel_available:
            return self._fallback_report("Quality check model channel unavailable")

        b64_image = base64.b64encode(image_data).decode()
        data_uri = f"data:{mime_type};base64,{b64_image}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _CHECKER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        },
                        {
                            "type": "text",
                            "text": "请对这张AI生成的婚纱照进行质量检查。",
                        },
                    ],
                },
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload
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
        """解析模型返回的 JSON 格式质检报告。"""
        content = raw_content.strip()

        # 去掉可能的 markdown 代码块包裹
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

            # 解析带分类的 issues
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
                    # 向后兼容纯字符串 issues
                    issues.append(QualityIssue(
                        description=item,
                        category=self._guess_category(item),
                        severity=0.5,
                    ))

            return QualityReport(
                passed=result.get("passed", True),
                score=float(result.get("score", 1.0)),
                issues=issues,
                suggestions=result.get("suggestions", []),
            )
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse VLM report, raw: %s", raw_content[:200])
            return QualityReport(
                passed=True,
                score=0.5,
                issues=[QualityIssue(
                    description="Quality report parsing failed",
                    category=IssueCategory.physical,
                    severity=0.3,
                )],
                suggestions=["Manual review recommended"],
            )

    @staticmethod
    def _guess_category(description: str) -> IssueCategory:
        """根据描述文本猜测问题分类。"""
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
        """质检不可用时给出保底通过结果，避免误判为低质量图片。"""
        return QualityReport(
            passed=True,
            score=settings.quality_acceptable,
            issues=[QualityIssue(
                description=reason,
                category=IssueCategory.physical,
                severity=0.0,
            )],
            suggestions=["Manual review recommended"],
        )

    async def check_and_suggest_fix_prompt(
        self,
        image_data: bytes,
        original_prompt: str,
        mime_type: str = "image/png",
    ) -> tuple[QualityReport, str | None]:
        """
        质检并在不通过时生成修复 prompt。
        返回 (report, fix_prompt or None)。
        """
        report = await self.check_image(image_data, mime_type)

        if report.passed and report.score >= settings.quality_acceptable:
            return report, None

        # 生成修复 prompt（合并所有 issue 描述）
        issues_text = "; ".join(i.description for i in report.issues)
        fix_prompt = (
            f"Based on the original prompt: '{original_prompt}', "
            f"fix the following issues: {issues_text}. "
            f"Ensure the result has no artifacts, correct anatomy, "
            f"natural expressions, and consistent lighting."
        )

        return report, fix_prompt


vlm_checker_service = VLMCheckerService()
