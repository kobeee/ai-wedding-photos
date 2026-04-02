from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from io import BytesIO

import httpx
from PIL import Image, ImageOps

from config import settings

logger = logging.getLogger(__name__)

SLOT_CONFIG: dict[str, dict[str, str | bool]] = {
    "groom_portrait": {
        "role": "groom",
        "required": True,
        "label": "新郎正脸半身",
        "requirement": "one Chinese groom, front-facing upper-body portrait, clear face, casual daily photo",
    },
    "groom_full": {
        "role": "groom",
        "required": True,
        "label": "新郎全身",
        "requirement": "the same Chinese groom, full-body standing photo, body proportions visible, casual daily photo",
    },
    "bride_portrait": {
        "role": "bride",
        "required": True,
        "label": "新娘正脸半身",
        "requirement": "one Chinese bride, front-facing upper-body portrait, clear face, casual daily photo",
    },
    "bride_full": {
        "role": "bride",
        "required": True,
        "label": "新娘全身",
        "requirement": "the same Chinese bride, full-body standing photo, body proportions visible, casual daily photo",
    },
    "couple_full": {
        "role": "couple",
        "required": False,
        "label": "双人全身合照",
        "requirement": "the same Chinese couple together, both visible, full-body standing photo, casual daily photo",
    },
}

REQUIRED_SLOTS = {
    slot_id for slot_id, config in SLOT_CONFIG.items() if bool(config["required"])
}

AI_VALIDATION_SLOT_PRIORITY = {
    "groom_portrait": 0,
    "bride_portrait": 1,
    "groom_full": 2,
    "bride_full": 3,
    "couple_full": 4,
}


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

_VALIDATION_SYSTEM_PROMPT = """\
You validate wedding-photo reference uploads before generation.

Be strict about composition and identity consistency, but only based on what is clearly visible.

Requirements:
- groom_portrait: one Chinese groom, front-facing upper-body or head-and-shoulders, face sharp and unobstructed
- groom_full: same groom, full body visible from head to feet, standing pose preferred
- bride_portrait: one Chinese bride, front-facing upper-body or head-and-shoulders, face sharp and unobstructed
- bride_full: same bride, full body visible from head to feet, standing pose preferred
- couple_full: optional, same groom and bride together, both visible, full-body daily photo

Return ONLY JSON:
{
  "slot_checks": {
    "groom_portrait": "pass|wrong_subject|not_portrait|too_blurry|unclear",
    "groom_full": "pass|wrong_subject|not_full_body|too_blurry|unclear",
    "bride_portrait": "pass|wrong_subject|not_portrait|too_blurry|unclear",
    "bride_full": "pass|wrong_subject|not_full_body|too_blurry|unclear",
    "couple_full": "pass|wrong_subject|not_full_body|not_couple|too_blurry|unclear"
  },
  "identity_checks": {
    "groom_pair_same_person": "pass|mismatch|unclear",
    "bride_pair_same_person": "pass|mismatch|unclear",
    "couple_matches_singles": "pass|mismatch|unclear|not_applicable"
  }
}

Rules:
- Use the status codes exactly as listed above.
- Use "pass" only when clearly acceptable.
- Use "unclear" when the image might be usable but confidence is low.
- Use "not_applicable" only when couple_full was not provided.
"""


@dataclass
class UploadBundleItem:
    slot: str
    role: str
    filename: str
    content: bytes
    mime_type: str


@dataclass
class UploadValidationIssue:
    level: str
    message: str
    slot: str = ""


@dataclass
class UploadValidationReport:
    ok: bool
    issues: list[UploadValidationIssue] = field(default_factory=list)
    slot_messages: dict[str, str] = field(default_factory=dict)
    identity_messages: dict[str, str] = field(default_factory=dict)
    source: str = "heuristic"

    @property
    def errors(self) -> list[UploadValidationIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[UploadValidationIssue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def slot_ok(self, slot: str) -> bool:
        return not any(issue.level == "error" and issue.slot == slot for issue in self.issues)

    def summary_text(self) -> str:
        messages = [issue.message for issue in self.errors[:3]]
        return "；".join(messages)


class UploadValidatorService:
    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/chat/completions"
        self.model = settings.vlm_model

    @staticmethod
    def validate_slots_schema(items: list[UploadBundleItem]) -> list[str]:
        errors: list[str] = []
        seen_slots: set[str] = set()

        for item in items:
            if item.slot not in SLOT_CONFIG:
                errors.append(f"不支持的上传坑位：{item.slot}")
                continue

            expected_role = str(SLOT_CONFIG[item.slot]["role"])
            if item.role != expected_role:
                errors.append(f"{SLOT_CONFIG[item.slot]['label']} 只能上传对应人物照片")

            if item.slot in seen_slots:
                errors.append(f"{SLOT_CONFIG[item.slot]['label']} 只能上传 1 张")
            seen_slots.add(item.slot)

        missing = [
            str(SLOT_CONFIG[slot]["label"])
            for slot in REQUIRED_SLOTS
            if slot not in seen_slots
        ]
        if missing:
            errors.append(f"缺少必传照片：{'、'.join(missing)}")

        return errors

    @staticmethod
    def _prepare_image(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
        try:
            with Image.open(BytesIO(image_data)) as image:
                image = ImageOps.exif_transpose(image)
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

                max_dim = max(settings.upload_validation_max_image_dimension, 640)
                if image.width > max_dim or image.height > max_dim:
                    image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                quality = settings.upload_validation_jpeg_quality
                min_quality = max(
                    min(settings.upload_validation_min_jpeg_quality, quality),
                    35,
                )

                while True:
                    buffer = BytesIO()
                    image.save(
                        buffer,
                        format="JPEG",
                        quality=quality,
                        optimize=True,
                    )
                    prepared = buffer.getvalue()
                    if len(prepared) <= settings.upload_validation_max_bytes:
                        return prepared, "image/jpeg"

                    if quality > min_quality:
                        quality -= 6
                        continue

                    long_edge = max(image.size)
                    if long_edge <= 512:
                        return prepared, "image/jpeg"

                    scaled_long_edge = max(512, int(round(long_edge * 0.85)))
                    scale = scaled_long_edge / max(long_edge, 1)
                    resized_width = max(1, int(round(image.width * scale)))
                    resized_height = max(1, int(round(image.height * scale)))
                    image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        except Exception:
            logger.warning("Failed to preprocess upload validation image", exc_info=True)
            return image_data, mime_type

    def _select_items_for_ai_validation(
        self,
        items: list[UploadBundleItem],
    ) -> list[tuple[UploadBundleItem, bytes, str]]:
        ordered_items = sorted(
            items,
            key=lambda item: AI_VALIDATION_SLOT_PRIORITY.get(item.slot, 99),
        )
        selected: list[tuple[UploadBundleItem, bytes, str]] = []
        total_bytes = 0
        max_images = max(settings.upload_validation_max_images, 1)
        byte_budget = max(
            settings.upload_validation_total_max_bytes,
            settings.upload_validation_max_bytes,
        )

        for item in ordered_items:
            if len(selected) >= max_images:
                logger.info(
                    "Skipped AI upload validation for slot %s because max image count %d was reached",
                    item.slot,
                    max_images,
                )
                break

            prepared, prepared_mime = self._prepare_image(item.content, item.mime_type)
            projected_total = total_bytes + len(prepared)
            if selected and projected_total > byte_budget:
                logger.info(
                    "Skipped AI upload validation for slot %s to keep payload within budget (%dKB > %dKB)",
                    item.slot,
                    projected_total // 1024,
                    byte_budget // 1024,
                )
                continue

            selected.append((item, prepared, prepared_mime))
            total_bytes = projected_total

        logger.info(
            "Prepared %d upload validation image(s), total=%dKB",
            len(selected),
            total_bytes // 1024,
        )
        return selected

    @staticmethod
    def _parse_json(raw: str) -> dict:
        return _load_first_json_object(raw)

    @staticmethod
    def _slot_status_message(slot: str, status: str) -> UploadValidationIssue | None:
        label = str(SLOT_CONFIG.get(slot, {}).get("label", slot))
        error_messages = {
            "wrong_subject": f"{label} 里的人不对，请换成对应人物照片",
            "not_portrait": f"{label} 不够接近，请换成正脸半身照",
            "not_full_body": f"{label} 不是完整全身，请换成头到脚清楚入镜的照片",
            "too_blurry": f"{label} 清晰度不够，请换一张更清楚的原图",
            "not_couple": f"{label} 里不像同时有两个人，请换一张双人合照",
        }
        warning_messages = {
            "unclear": f"{label} 识别把握不高，建议换一张更清晰更标准的照片",
        }

        if status in error_messages:
            return UploadValidationIssue("error", error_messages[status], slot)
        if status in warning_messages:
            return UploadValidationIssue("warning", warning_messages[status], slot)
        return None

    @staticmethod
    def _identity_status_issue(check_name: str, status: str) -> UploadValidationIssue | None:
        if status == "pass" or status == "not_applicable":
            return None

        if check_name == "groom_pair_same_person":
            if status == "mismatch":
                return UploadValidationIssue("error", "两张新郎照片不像同一个人，请替换其中一张", "groom_full")
            return UploadValidationIssue("warning", "新郎两张照片一致性不够稳，建议换一张更像本人的", "groom_full")

        if check_name == "bride_pair_same_person":
            if status == "mismatch":
                return UploadValidationIssue("error", "两张新娘照片不像同一个人，请替换其中一张", "bride_full")
            return UploadValidationIssue("warning", "新娘两张照片一致性不够稳，建议换一张更像本人的", "bride_full")

        if check_name == "couple_matches_singles":
            if status == "mismatch":
                return UploadValidationIssue("error", "双人合照和单人照不像同一对人，请换一张合照", "couple_full")
            return UploadValidationIssue("warning", "系统不太确定这张合照就是同一对人，建议换一张更清楚的双人照", "couple_full")

        return None

    def _heuristic_validate(self, items: list[UploadBundleItem]) -> UploadValidationReport:
        issues: list[UploadValidationIssue] = []
        slot_messages: dict[str, str] = {}

        for item in items:
            try:
                with Image.open(BytesIO(item.content)) as image:
                    width, height = image.size
            except Exception:
                issues.append(UploadValidationIssue("error", "照片无法识别，请换一张清晰原图", item.slot))
                continue

            short_side = min(width, height)
            long_side = max(width, height)
            ratio = long_side / max(short_side, 1)

            if short_side < 512:
                issues.append(UploadValidationIssue("error", "清晰度不足，请换一张更清晰的原图", item.slot))
                continue

            if item.slot.endswith("_portrait") and ratio > 1.8:
                issues.append(UploadValidationIssue("warning", "建议换成正脸半身照，面部再近一些", item.slot))
            elif item.slot.endswith("_full") and short_side < 720:
                issues.append(UploadValidationIssue("warning", "建议换成全身占比更大的照片，方便识别身形", item.slot))
            else:
                slot_messages[item.slot] = "基础清晰度通过"

        return UploadValidationReport(
            ok=not any(issue.level == "error" for issue in issues),
            issues=issues,
            slot_messages=slot_messages,
            source="heuristic",
        )

    async def validate(self, items: list[UploadBundleItem]) -> UploadValidationReport:
        schema_errors = self.validate_slots_schema(items)
        if schema_errors:
            return UploadValidationReport(
                ok=False,
                issues=[UploadValidationIssue("error", message) for message in schema_errors],
                source="schema",
            )

        heuristic_report = self._heuristic_validate(items)
        if heuristic_report.errors or not settings.chat_api_key:
            return heuristic_report

        user_content: list[dict] = [
            {
                "type": "text",
                "text": (
                    "请按坑位逐张校验这些参考图，并判断同角色两张是否像同一个人。"
                    "如果存在双人合照，再判断是否与单人照是同一对人。"
                ),
            }
        ]

        for item, prepared, prepared_mime in self._select_items_for_ai_validation(items):
            b64_image = base64.b64encode(prepared).decode()
            requirement = SLOT_CONFIG[item.slot]["requirement"]
            user_content.append(
                {
                    "type": "text",
                    "text": f"{item.slot}: {requirement}",
                }
            )
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{prepared_mime};base64,{b64_image}"},
                }
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": settings.upload_validation_max_tokens,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.upload_validation_timeout_seconds)
            ) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {settings.chat_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()

            data = self._parse_json(response.json()["choices"][0]["message"]["content"])
            issues: list[UploadValidationIssue] = []
            slot_messages: dict[str, str] = {}
            for slot, status_raw in dict(data.get("slot_checks", {})).items():
                status = str(status_raw or "").strip().lower()
                issue = self._slot_status_message(slot, status)
                if issue:
                    issues.append(issue)
                elif status == "pass":
                    slot_messages[slot] = "AI 校验通过"

            identity_messages: dict[str, str] = {}
            for check_name, status_raw in dict(data.get("identity_checks", {})).items():
                status = str(status_raw or "").strip().lower()
                issue = self._identity_status_issue(check_name, status)
                if issue:
                    issues.append(issue)
                elif status == "pass":
                    identity_messages[check_name] = "AI 一致性通过"

            return UploadValidationReport(
                ok=not any(issue.level == "error" for issue in issues),
                issues=issues,
                slot_messages=slot_messages,
                identity_messages=identity_messages,
                source="ai",
            )
        except Exception:
            logger.exception("Upload AI validation failed, falling back to heuristic validation")
            return heuristic_report


upload_validator_service = UploadValidatorService()
