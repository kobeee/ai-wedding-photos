"""Director 编辑模式 — 只在有用户偏好时调用 LLM 微调 Brief。

Phase 3 升级：
- 不再从零生成 CameraSchema
- 输入：基础 brief + 用户偏好 → 输出：微调后的 brief 字段
- 无偏好时不调用 LLM（零成本）
- allowed_edit_scope 限制 LLM 可编辑的字段
- 保留旧 API 向后兼容（direct 方法）
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from config import settings
from context import (
    assemble_generation_prompt,
    get_brief,
    get_variants,
    render_slots,
)
from context.briefs import CreativeBrief
from models.schemas import CameraSchema

logger = logging.getLogger(__name__)

_UNAVAILABLE_CHANNEL_MARKERS = (
    "无可用渠道",
    "no available channel",
)

# Director 允许编辑的字段（保住核心叙事，只改边缘）
_ALLOWED_EDIT_FIELDS = {
    "makeup_default", "wardrobe_bride", "wardrobe_groom",
    "pose_energy", "lighting_bias",
}
_FORBIDDEN_EDIT_FIELDS = {"package_id", "story", "visual_essence"}

_EDITOR_SYSTEM_PROMPT = """\
You are a wedding photography creative director. You receive a pre-written \
creative brief and user preferences. Your job is to EDIT specific fields \
of the brief to incorporate the user's preferences.

Rules:
1. Only modify the fields listed in "editable_fields"
2. NEVER change the story or visual_essence — those define the package identity
3. Keep all values in English
4. Be concise — each field should be 1-2 sentences max
5. If a preference doesn't apply to any editable field, ignore it

Return ONLY a JSON object with the fields you want to change. \
If no changes needed, return {}. No markdown, no explanation.\
"""

_RETRY_APPEND_PROMPT = (
    "\n\nPrevious response was not valid JSON. "
    "Return one compact JSON object only, with double-quoted keys and string values."
)


class DirectorService:
    """Director 编辑模式 — 微调 CreativeBrief 的边缘字段。"""

    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/chat/completions"
        self._channel_available = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.chat_api_key}",
            "Content-Type": "application/json",
        }

    async def edit_brief(
        self,
        brief: CreativeBrief,
        preferences: dict,
    ) -> CreativeBrief:
        """用 LLM 根据用户偏好微调 brief。

        只在有用户偏好时调用。无偏好时直接返回原 brief，不调 LLM。
        """
        if not preferences:
            return brief

        if not settings.chat_api_key or not self._channel_available:
            logger.info("Director unavailable, returning base brief")
            return brief

        user_msg = (
            f"Creative brief for package '{brief.package_id}':\n"
            f"- story: {brief.story}\n"
            f"- wardrobe_bride: {brief.wardrobe_bride}\n"
            f"- wardrobe_groom: {brief.wardrobe_groom}\n"
            f"- makeup_default: {brief.makeup_default}\n"
            f"- pose_energy: {brief.pose_energy}\n"
            f"- lighting_bias: {brief.lighting_bias}\n"
            f"\n"
            f"Editable fields: {sorted(_ALLOWED_EDIT_FIELDS)}\n"
            f"\n"
            f"User preferences: {json.dumps(preferences, ensure_ascii=False)}\n"
            f"\n"
            f"Return a JSON with only the fields to change."
        )

        try:
            edits = await self._request_edits(user_msg)
            return self._apply_edits(brief, edits)
        except Exception:
            logger.exception("Director edit failed, returning base brief")
            return brief

    async def _request_edits(self, user_msg: str) -> dict:
        user_content = user_msg
        for attempt in range(2):
            payload = {
                "model": settings.director_model,
                "messages": [
                    {"role": "system", "content": _EDITOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 512,
                "temperature": 0.1,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload,
                )

                if resp.status_code >= 400:
                    self._maybe_disable_channel(resp)
                    resp.raise_for_status()

                data = resp.json()

            raw = data["choices"][0]["message"]["content"].strip()
            try:
                return self._parse_edits_payload(raw)
            except json.JSONDecodeError:
                logger.warning(
                    "Director returned invalid JSON on attempt %d: %s",
                    attempt + 1,
                    raw[:200],
                )
                user_content = user_msg + _RETRY_APPEND_PROMPT

        return {}

    @staticmethod
    def _parse_edits_payload(raw: str) -> dict:
        """尽量从 LLM 输出中提取 JSON 对象。"""
        cleaned = raw.strip()

        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
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
            cleaned = "\n".join(json_lines).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    parsed = DirectorService._salvage_partial_key_values(cleaned)
            else:
                parsed = DirectorService._salvage_partial_key_values(cleaned)

        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Director payload is not a JSON object", cleaned, 0)
        return parsed

    @staticmethod
    def _salvage_partial_key_values(raw: str) -> dict:
        """从不完整 JSON 中兜底提取简单的 key/value。"""
        matches = re.findall(r'"([^"]+)"\s*:\s*"([^"\n}]*)', raw)
        if not matches:
            raise json.JSONDecodeError("Unable to salvage director payload", raw, 0)
        return {key: value.strip().rstrip(",") for key, value in matches if value.strip()}

    def _apply_edits(self, brief: CreativeBrief, edits: dict) -> CreativeBrief:
        """安全地把 LLM 的编辑应用到 brief 上。"""
        if not edits or not isinstance(edits, dict):
            return brief

        result = brief.model_copy(deep=True)

        for key, value in edits.items():
            # 安全检查：只允许编辑白名单字段
            if key in _FORBIDDEN_EDIT_FIELDS:
                logger.warning("Director tried to edit forbidden field: %s", key)
                continue
            if key not in _ALLOWED_EDIT_FIELDS:
                logger.debug("Director tried to edit unknown field: %s", key)
                continue
            if not isinstance(value, str):
                continue

            setattr(result, key, value)

        return result

    async def direct(
        self,
        package_id: str,
        makeup_style: str = "natural",
        gender: str = "couple",
        preferences: dict | None = None,
    ) -> tuple[CameraSchema, str]:
        """旧接口兼容层。

        返回一个最接近旧语义的 CameraSchema 以及按新上下文工程组装的 prompt，
        供 ACP/旧调用方继续运行，避免运行时断裂。
        """
        brief = get_brief(package_id)
        if preferences:
            brief = await self.edit_brief(brief, preferences)

        slots = render_slots(
            makeup_style=makeup_style,
            gender=gender,
            preferences=preferences,
        )
        variant = get_variants(brief, count=1)[0]
        prompt = assemble_generation_prompt(
            brief=brief,
            variant=variant,
            slots=slots,
            has_refs=True,
            has_couple_refs=(gender == "couple"),
        )

        legacy_schema = CameraSchema(
            scene=brief.visual_essence,
            lighting=brief.lighting_bias.replace("_", " ") or brief.aesthetic,
            composition=f"{variant.framing} frame, {variant.action}",
            lens=f"Editorial wedding framing with {brief.shot_scale} scale",
            mood=brief.emotion,
            wardrobe="; ".join(
                part for part in (brief.wardrobe_bride, brief.wardrobe_groom) if part
            ),
            pose_direction=variant.action,
        )
        return legacy_schema, prompt

    def _maybe_disable_channel(self, response: httpx.Response) -> None:
        try:
            data = response.json()
        except ValueError:
            return
        message = str(data.get("error", {}).get("message", "")).lower()
        if any(marker in message for marker in _UNAVAILABLE_CHANNEL_MARKERS):
            self._channel_available = False
            logger.warning(
                "Director model channel unavailable for model %s; "
                "future requests will use local fallback.",
                settings.director_model,
            )


director_service = DirectorService()
