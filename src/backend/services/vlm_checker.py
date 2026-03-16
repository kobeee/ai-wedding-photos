from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field

import httpx

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """图片质检结果。"""
    passed: bool = True
    score: float = 1.0  # 0.0 ~ 1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# 质检用的系统 prompt
_CHECKER_SYSTEM_PROMPT = """你是一个专业的婚纱照质检AI。请仔细检查这张AI生成的婚纱照，判断是否存在以下问题：

1. 手指畸形（多指、少指、扭曲）
2. 面部异常（五官变形、不对称、表情僵硬）
3. 穿模问题（衣物穿过身体、首饰嵌入皮肤）
4. 比例失调（头身比异常、四肢长度不对）
5. 背景穿帮（不合理的物体、文字、水印）
6. 光影错误（光源方向不一致、阴影缺失或错位）
7. 边缘瑕疵（模糊过渡、锯齿、不自然的融合）

请用JSON格式返回结果：
{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": ["问题1描述", "问题2描述"],
  "suggestions": ["修复建议1", "修复建议2"]
}

如果图片质量优秀无明显问题，score >= 0.8 且 passed = true。
如果存在轻微问题但可接受，score 0.5-0.8，passed = true，但列出issues。
如果存在严重问题，score < 0.5，passed = false。
"""


class VLMCheckerService:
    """
    VLM 质检服务。
    利用多模态大模型检测 AI 生成婚纱照中的瑕疵。
    通过 laozhang.ai 代理调用 ChatCompletion with vision。
    """

    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.laozhang_api_key}",
            "Content-Type": "application/json",
        }
        # 用于质检的模型，用 gpt-4o 级别就够
        self.model = "gpt-4o"

    def _check_api_key(self) -> None:
        if not settings.laozhang_api_key:
            raise RuntimeError(
                "laozhang_api_key is not configured. "
                "Set LAOZHANG_API_KEY in .env or environment variables."
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
                    self.api_url, headers=self.headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            return self._parse_report(content)

        except Exception:
            logger.exception("VLM quality check failed")
            # 质检服务异常时默认通过，避免阻塞流程
            return QualityReport(
                passed=True,
                score=0.0,
                issues=["Quality check service unavailable"],
                suggestions=["Manual review recommended"],
            )

    def _parse_report(self, raw_content: str) -> QualityReport:
        """解析模型返回的 JSON 格式质检报告。"""
        import json

        # 尝试从返回内容中提取 JSON
        content = raw_content.strip()

        # 去掉可能的 markdown 代码块包裹
        if content.startswith("```"):
            lines = content.split("\n")
            # 去掉首尾的 ``` 行
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
            return QualityReport(
                passed=result.get("passed", True),
                score=float(result.get("score", 1.0)),
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", []),
            )
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse VLM report, raw: %s", raw_content[:200])
            return QualityReport(
                passed=True,
                score=0.5,
                issues=["Quality report parsing failed"],
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

        if report.passed:
            return report, None

        # 生成修复 prompt
        issues_text = "; ".join(report.issues)
        fix_prompt = (
            f"Based on the original prompt: '{original_prompt}', "
            f"fix the following issues: {issues_text}. "
            f"Ensure the result has no artifacts, correct anatomy, "
            f"natural expressions, and consistent lighting."
        )

        return report, fix_prompt


vlm_checker_service = VLMCheckerService()
