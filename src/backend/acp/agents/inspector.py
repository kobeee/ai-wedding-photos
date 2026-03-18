"""VLM Inspector Agent — 图片质量检测。"""

import base64
import logging

from acp_sdk.server import Context
from acp_sdk.models import Message, MessagePart, Metadata

from acp.server import server

logger = logging.getLogger(__name__)


@server.agent(
    name="quality-inspector",
    description=(
        "VLM 质检员 — 检测 AI 生成婚纱照的物理错误"
        "和情绪问题，给出修复建议。"
    ),
    metadata=Metadata(tags=["wedding", "quality-check", "vlm"]),
)
async def quality_inspector(
    input: list[Message], context: Context
):
    """VLM 质检 Agent — 检测图片质量问题。"""
    yield {"thought": "正在进行质量检测..."}

    image_data: bytes | None = None
    for msg in input:
        for part in msg.parts:
            if hasattr(part, "data"):
                image_data = (
                    base64.b64decode(part.data)
                    if isinstance(part.data, str)
                    else part.data
                )
                break
        if image_data:
            break

    if not image_data:
        yield Message(
            parts=[MessagePart(text="请提供需要质检的图片。")]
        )
        return

    from services.vlm_checker import vlm_checker_service

    report, fix_prompt = (
        await vlm_checker_service.check_and_suggest_fix_prompt(
            image_data=image_data,
            original_prompt="wedding photo quality check",
        )
    )

    result_text = (
        f"质检结果：{'通过' if report.passed else '未通过'}\n"
        f"质量评分：{report.score:.2f}\n"
    )
    if report.issues:
        issues_str = "\n".join(
            f"  - {issue}" for issue in report.issues
        )
        result_text += f"发现问题：\n{issues_str}\n"
    if report.suggestions:
        sugg_str = "\n".join(
            f"  - {s}" for s in report.suggestions
        )
        result_text += f"修复建议：\n{sugg_str}\n"
    if fix_prompt:
        result_text += f"\n自动修复 Prompt：{fix_prompt}"

    yield Message(parts=[MessagePart(text=result_text)])
