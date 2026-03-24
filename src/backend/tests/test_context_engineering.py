from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from context.briefs import get_brief
from context.prompt_assembler import assemble_generation_prompt
from context.reference_selector import select_references
from context.slot_renderer import render_slots
from context.thresholds import RepairMode, decide_repair, meets_delivery_floor
from services.director import director_service
from services.vlm_checker import VLMCheckerService
from utils.storage import upload_metadata_path


def _make_image_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


class ContextEngineeringTests(unittest.TestCase):
    def test_thresholds_reject_final_round_for_identity_low(self) -> None:
        decision = decide_repair(
            hard_fail=False,
            identity_match=0.45,
            brief_alignment=0.82,
            aesthetic_score=0.81,
            fix_round=2,
            max_rounds=3,
        )
        self.assertEqual(decision.mode, RepairMode.reject)

    def test_thresholds_reject_final_round_for_hard_fail(self) -> None:
        decision = decide_repair(
            hard_fail=True,
            identity_match=0.92,
            brief_alignment=0.86,
            aesthetic_score=0.83,
            fix_round=1,
            max_rounds=2,
        )
        self.assertEqual(decision.mode, RepairMode.reject)

    def test_thresholds_reject_low_scoring_soft_fail_on_final_round(self) -> None:
        decision = decide_repair(
            hard_fail=False,
            identity_match=0.78,
            brief_alignment=0.41,
            aesthetic_score=0.31,
            fix_round=2,
            max_rounds=3,
        )
        self.assertEqual(decision.mode, RepairMode.reject)

    def test_thresholds_allow_borderline_soft_pass_on_final_round(self) -> None:
        decision = decide_repair(
            hard_fail=False,
            identity_match=0.84,
            brief_alignment=0.71,
            aesthetic_score=0.69,
            fix_round=2,
            max_rounds=3,
        )
        self.assertEqual(decision.mode, RepairMode.deliver)

    def test_delivery_floor_blocks_low_score(self) -> None:
        self.assertFalse(meets_delivery_floor(0.50))
        self.assertTrue(meets_delivery_floor(0.72))

    def test_reference_selector_keeps_bride_and_groom_when_metadata_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            samples = [
                ("bride", _make_image_bytes((1200, 1600), (240, 210, 210))),
                ("groom", _make_image_bytes((1200, 1600), (120, 120, 140))),
                ("unknown", _make_image_bytes((900, 1200), (180, 180, 180))),
            ]

            for index, (role, data) in enumerate(samples):
                image_path = upload_dir / f"sample_{index}.jpg"
                image_path.write_bytes(data)
                upload_metadata_path(image_path).write_text(
                    json.dumps({"role": role}, ensure_ascii=False),
                    encoding="utf-8",
                )

            selected = select_references(upload_dir)

        self.assertTrue(selected.has_identity)
        self.assertTrue(selected.has_couple_identity)
        self.assertEqual(selected.selected_role_counts["bride"], 1)
        self.assertEqual(selected.selected_role_counts["groom"], 1)
        self.assertLessEqual(selected.count, 3)

    def test_prompt_assembler_uses_generic_couple_anchor_when_refs_are_incomplete(self) -> None:
        brief = get_brief("iceland")
        variant = brief.variants[0]
        slots = render_slots(gender="couple")

        prompt = assemble_generation_prompt(
            brief=brief,
            variant=variant,
            slots=slots,
            has_refs=True,
            has_couple_refs=False,
        )

        self.assertIn("identity guidance for this wedding portrait", prompt)
        self.assertNotIn("real bride and groom", prompt)

    def test_vlm_fallback_blocks_delivery(self) -> None:
        report = VLMCheckerService._fallback_report("service unavailable")
        self.assertFalse(report.passed)
        self.assertTrue(report.inspection_unavailable)
        self.assertEqual(report.score, 0.0)

    def test_director_compatibility_api_returns_prompt(self) -> None:
        schema, prompt = asyncio.run(
            director_service.direct(
                package_id="iceland",
                makeup_style="natural",
                gender="couple",
            ),
        )

        self.assertTrue(schema.scene)
        self.assertIn("world-class wedding photographer", prompt)
        self.assertIn("The subjects are a bride and groom.", prompt)

    def test_director_parser_extracts_json_from_code_fence(self) -> None:
        parsed = director_service._parse_edits_payload(
            "```json\n{\"wardrobe_bride\":\"silk gown\"}\n```"
        )
        self.assertEqual(parsed["wardrobe_bride"], "silk gown")

    def test_director_parser_extracts_json_from_noisy_text(self) -> None:
        parsed = director_service._parse_edits_payload(
            "Use this edit:\n{\"lighting_bias\":\"golden rim light\"}\nThanks."
        )
        self.assertEqual(parsed["lighting_bias"], "golden rim light")

    def test_director_parser_salvages_truncated_value(self) -> None:
        parsed = director_service._parse_edits_payload(
            '{\n  "wardrobe_bride": "Flowing white gown accented with soft pearl styling,\n'
        )
        self.assertEqual(
            parsed["wardrobe_bride"],
            "Flowing white gown accented with soft pearl styling",
        )


if __name__ == "__main__":
    unittest.main()
