"""AI Makeup Agent — 试妆预览。"""

import base64
import logging

from acp_sdk.server import Context
from acp_sdk.models import Message, MessagePart, Metadata

from acp.server import server

logger = logging.getLogger(__name__)

_STYLES = {
    "natural": "素颜清透",
    "refined": "精致妆容",
    "sculpt": "骨相微调",
}


@server.agent(
    name="makeup-artist",
    description=(
        "AI 试妆师 — 提供素颜清透、精致妆容、"
        "骨相微调三种风格预览。"
    ),
    metadata=Metadata(tags=["wedding", "makeup", "ai"]),
)
async def makeup_artist(
    input: list[Message], context: Context
):
    """AI 试妆 Agent — 生成 3 种妆造风格预览。"""
    yield {"thought": "正在准备试妆方案..."}

    text_content = ""
    image_data: bytes | None = None
    for msg in input:
        for part in msg.parts:
            if hasattr(part, "text"):
                text_content += part.text
            elif hasattr(part, "data"):
                image_data = (
                    base64.b64decode(part.data)
                    if isinstance(part.data, str)
                    else part.data
                )

    gender = "female"
    if (
        "male" in text_content.lower()
        and "female" not in text_content.lower()
    ):
        gender = "male"

    from services.nano_banana import nano_banana_service

    results: list[tuple[str, str]] = []
    for style_key, style_name in _STYLES.items():
        yield {"thought": f"正在生成 {style_name} 效果..."}
        prompt = (
            f"Professional wedding portrait, {gender}, "
            f"{style_key} makeup style, elegant, 8K quality"
        )
        try:
            if image_data:
                img = await nano_banana_service.image_to_image(
                    prompt=prompt, image_data=image_data,
                )
            else:
                img = await nano_banana_service.text_to_image(
                    prompt=prompt,
                )
            results.append(
                (style_name, base64.b64encode(img).decode())
            )
        except Exception as e:
            logger.warning(
                "Makeup generation failed for %s: %s",
                style_key, e,
            )

    parts: list[MessagePart] = [
        MessagePart(
            text=f"试妆完成！共生成 {len(results)} 种风格："
        ),
    ]
    for name, b64 in results:
        parts.append(MessagePart(text=f"\n{name}:"))
        parts.append(
            MessagePart(data=b64, content_type="image/png")
        )

    yield Message(parts=parts)
