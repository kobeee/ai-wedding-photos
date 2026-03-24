"""Wedding Photographer Agent — 完整婚纱照生成流程。"""

import base64
import logging

from acp_sdk.server import Context
from acp_sdk.models import Message, MessagePart, Metadata, Capability

from acp.server import server

logger = logging.getLogger(__name__)


@server.agent(
    name="wedding-photographer",
    description=(
        "AI 婚纱摄影师 — 上传人像照片，选择风格套餐，"
        "AI 自动生成影楼级婚纱照。"
        "支持多种场景风格、AI 试妆、VLM 质检自动修复。"
    ),
    metadata=Metadata(
        tags=["wedding", "photography", "ai"],
        capabilities=[
            Capability(name="text-to-image", description="文生图"),
            Capability(name="image-to-image", description="图生图"),
            Capability(name="quality-check", description="VLM 质检"),
        ],
    ),
)
async def wedding_photographer(
    input: list[Message], context: Context
):
    """
    AI 婚纱摄影师 Agent。

    输入格式（text message）:
      package_id   — 套餐 ID
      makeup_style — 妆造风格
      gender       — 性别
    也可附带图片作为参考照片。
    """
    yield {"thought": "正在解析拍摄需求..."}

    # ---- 解析输入 ----
    text_content = ""
    image_parts: list = []
    for msg in input:
        for part in msg.parts:
            if hasattr(part, "text"):
                text_content += part.text + "\n"
            elif hasattr(part, "data"):
                image_parts.append(part)

    params = _parse_shoot_params(text_content)
    package_id = params.get("package_id", "iceland")
    makeup_style = params.get("makeup_style", "natural")
    gender = params.get("gender", "female")

    yield {"thought": f"拍摄方案：{package_id} 套餐，{makeup_style} 妆造"}

    # ---- Step 1: Director 生成 Camera Schema ----
    yield {"thought": "正在为您布光取景..."}
    render_prompt: str = ""
    try:
        from services.director import director_service

        camera_schema, render_prompt = await director_service.direct(
            package_id=package_id,
            makeup_style=makeup_style,
            gender=gender,
        )
        yield {
            "thought": f"场景：{camera_schema.scene}，"
            f"光线：{camera_schema.lighting}"
        }
    except Exception as e:
        logger.warning("Director service failed, using fallback: %s", e)
        render_prompt = (
            f"Professional wedding photo, {package_id} style, "
            f"{makeup_style} makeup, elegant and romantic, 8K quality"
        )

    # ---- Step 2: 生成底图 ----
    yield {"thought": "正在生成婚纱照底图..."}
    try:
        from services.nano_banana import nano_banana_service

        if image_parts:
            ref_data = (
                base64.b64decode(image_parts[0].data)
                if hasattr(image_parts[0], "data")
                else b""
            )
            if ref_data:
                img_bytes = await nano_banana_service.image_to_image(
                    prompt=render_prompt,
                    image_data=ref_data,
                )
            else:
                img_bytes = await nano_banana_service.text_to_image(
                    prompt=render_prompt,
                )
        else:
            img_bytes = await nano_banana_service.text_to_image(
                prompt=render_prompt,
            )
    except Exception as e:
        yield Message(
            parts=[MessagePart(text=f"生成失败：{e}")]
        )
        return

    # ---- Step 3: VLM 质检 + 修复循环 ----
    yield {"thought": "正在进行质量检测..."}
    try:
        from services.vlm_checker import vlm_checker_service

        for round_num in range(3):
            report, fix_prompt = (
                await vlm_checker_service.check_and_suggest_fix_prompt(
                    image_data=img_bytes,
                    original_prompt=render_prompt,
                )
            )
            if report.passed and report.score >= 0.85:
                break
            if report.inspection_unavailable:
                break
            if fix_prompt:
                yield {
                    "thought": f"第 {round_num + 1} 轮修复中..."
                }
                img_bytes = (
                    await nano_banana_service.image_to_image(
                        prompt=fix_prompt,
                        image_data=img_bytes,
                    )
                )
    except Exception as e:
        logger.warning("Quality check failed: %s", e)

    # ---- Step 4: 保存并返回 ----
    yield {"thought": "拍摄完成，正在交付成片..."}

    b64_result = base64.b64encode(img_bytes).decode()

    yield Message(
        parts=[
            MessagePart(
                text=(
                    f"婚纱照生成完成！"
                    f"套餐：{package_id}，妆造：{makeup_style}"
                ),
            ),
            MessagePart(
                data=b64_result,
                content_type="image/png",
            ),
        ]
    )


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

_PACKAGES = [
    "iceland", "french", "cyberpunk", "minimal",
    "onsen", "starcamp", "chinese-classic",
    "western-romantic", "artistic-fantasy",
    "travel-destination",
]

_MAKEUP_STYLES = ["natural", "refined", "sculpt"]


def _parse_shoot_params(text: str) -> dict:
    """从文本中提取拍摄参数。"""
    params: dict[str, str] = {}
    text_lower = text.lower()

    for pkg in _PACKAGES:
        if pkg in text_lower:
            params["package_id"] = pkg
            break

    for style in _MAKEUP_STYLES:
        if style in text_lower:
            params["makeup_style"] = style
            break

    if "male" in text_lower and "female" not in text_lower:
        params["gender"] = "male"
    elif "female" in text_lower:
        params["gender"] = "female"

    return params
