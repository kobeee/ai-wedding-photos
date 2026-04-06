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
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_nano_repair_prompt,
)
from context.reference_selector import select_references
from context.slot_renderer import render_slots
from context.thresholds import RepairMode, decide_repair, meets_delivery_floor
from services.delivery_image import _prepare_delivery_image_sync
from services.director import director_service
from services.nano_banana import NanoBananaService
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

    def test_thresholds_attempt_local_fix_when_hard_fail_has_retry_budget(self) -> None:
        decision = decide_repair(
            hard_fail=True,
            identity_match=0.92,
            brief_alignment=0.86,
            aesthetic_score=0.83,
            fix_round=0,
            max_rounds=2,
        )
        self.assertEqual(decision.mode, RepairMode.local_fix)

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
        # SSS floor: MIN_DELIVERY_FLOOR = 0.85, avg must be >= 0.85
        decision = decide_repair(
            hard_fail=False,
            identity_match=0.88,
            brief_alignment=0.86,
            aesthetic_score=0.83,
            fix_round=2,
            max_rounds=3,
        )
        # avg = (0.88+0.86+0.83)/3 = 0.8567 >= 0.85 → deliver
        self.assertEqual(decision.mode, RepairMode.deliver)

    def test_hero_track_relaxed_identity_floor(self) -> None:
        # Hero track: identity 0.72 >= HERO_IDENTITY_MATCH_FLOOR(0.70) → 不会 regenerate
        # Validation track: 0.72 < IDENTITY_MATCH_FLOOR(0.80) → regenerate
        hero_decision = decide_repair(
            hard_fail=False,
            identity_match=0.72,
            brief_alignment=0.86,
            aesthetic_score=0.88,
            fix_round=0,
            max_rounds=3,
            track="hero",
        )
        val_decision = decide_repair(
            hard_fail=False,
            identity_match=0.72,
            brief_alignment=0.86,
            aesthetic_score=0.88,
            fix_round=0,
            max_rounds=3,
            track="validation",
        )
        self.assertNotEqual(hero_decision.mode, RepairMode.regenerate)
        self.assertEqual(val_decision.mode, RepairMode.regenerate)

    def test_hero_track_relaxed_soft_pass_floor(self) -> None:
        # avg = (0.85+0.86+0.85)/3 = 0.853 >= HERO_SOFT_PASS_FLOOR(0.85) → deliver
        # Same scores on validation: 0.853 < SOFT_PASS_FLOOR(0.90) → local_fix
        hero_decision = decide_repair(
            hard_fail=False,
            identity_match=0.85,
            brief_alignment=0.86,
            aesthetic_score=0.85,
            fix_round=0,
            max_rounds=3,
            track="hero",
        )
        val_decision = decide_repair(
            hard_fail=False,
            identity_match=0.85,
            brief_alignment=0.86,
            aesthetic_score=0.85,
            fix_round=0,
            max_rounds=3,
            track="validation",
        )
        self.assertEqual(hero_decision.mode, RepairMode.deliver)
        self.assertEqual(val_decision.mode, RepairMode.local_fix)

    def test_hero_track_relaxed_delivery_floor(self) -> None:
        # avg = (0.82+0.80+0.79)/3 = 0.803 >= HERO_MIN_DELIVERY_FLOOR(0.80) → deliver on final
        # Same on validation: 0.803 < MIN_DELIVERY_FLOOR(0.85) → reject
        hero_decision = decide_repair(
            hard_fail=False,
            identity_match=0.82,
            brief_alignment=0.80,
            aesthetic_score=0.79,
            fix_round=2,
            max_rounds=3,
            track="hero",
        )
        val_decision = decide_repair(
            hard_fail=False,
            identity_match=0.82,
            brief_alignment=0.80,
            aesthetic_score=0.79,
            fix_round=2,
            max_rounds=3,
            track="validation",
        )
        self.assertEqual(hero_decision.mode, RepairMode.deliver)
        self.assertEqual(val_decision.mode, RepairMode.reject)

    def test_delivery_floor_blocks_low_score(self) -> None:
        self.assertFalse(meets_delivery_floor(0.50))
        self.assertFalse(meets_delivery_floor(0.84))  # below 0.85
        self.assertTrue(meets_delivery_floor(0.85))

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

    def test_reference_selector_prioritizes_couple_anchor_before_single_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            samples = [
                ("couple", _make_image_bytes((1200, 1600), (210, 190, 180))),
                ("bride", _make_image_bytes((1180, 1580), (240, 210, 210))),
                ("groom", _make_image_bytes((1160, 1560), (120, 120, 140))),
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

        self.assertTrue(selected.has_couple_anchor)
        self.assertEqual(selected.primary[0].role, "couple")
        self.assertEqual({selected.primary[1].role, selected.primary[2].role}, {"bride", "groom"})
        self.assertEqual(selected.selected_role_counts["couple"], 1)
        self.assertLessEqual(selected.count, 4)

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

    def test_prompt_assembler_adds_weak_body_anchor_only_when_couple_photo_exists(self) -> None:
        brief = get_brief("iceland")
        variant = brief.variants[0]
        slots = render_slots(gender="couple")

        prompt = assemble_generation_prompt(
            brief=brief,
            variant=variant,
            slots=slots,
            has_refs=True,
            has_couple_refs=True,
            has_couple_anchor=True,
        )

        self.assertIn("The first reference image is a full-body couple photo.", prompt)

    def test_prompt_assembler_blocks_mirrored_profiles_for_close_couple(self) -> None:
        brief = get_brief("iceland")
        variant = brief.variants[0]
        slots = render_slots(gender="couple")

        prompt = assemble_generation_prompt(
            brief=brief,
            variant=variant,
            slots=slots,
            has_refs=True,
            has_couple_refs=True,
            has_couple_anchor=True,
        )

        self.assertIn("mirrored side profiles", prompt)
        self.assertIn("both faces readable in open three-quarter view", prompt)
        self.assertIn("both eyes visible", prompt)
        self.assertIn("Standing close with shoulders opened slightly toward camera", prompt)

    def test_vlm_fallback_blocks_delivery(self) -> None:
        report = VLMCheckerService._fallback_report("service unavailable")
        self.assertFalse(report.passed)
        self.assertTrue(report.inspection_unavailable)
        self.assertEqual(report.score, 0.0)

    def test_vlm_prepare_image_for_request_downsizes_and_converts_to_jpeg(self) -> None:
        image = Image.new("RGBA", (2400, 3200), (255, 240, 230, 180))
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        prepared, mime_type, original_size, prepared_size = (
            VLMCheckerService._prepare_image_for_request(
                buffer.getvalue(),
                "image/png",
            )
        )

        self.assertEqual(mime_type, "image/jpeg")
        self.assertEqual(original_size, (2400, 3200))
        self.assertIsNotNone(prepared_size)
        assert prepared_size is not None
        self.assertLessEqual(max(prepared_size), 1536)
        self.assertGreater(len(prepared), 0)

    def test_vlm_parse_report_tolerates_fenced_json(self) -> None:
        report = VLMCheckerService()._parse_report(
            """```json
            {
              "hard_fail": false,
              "identity_match": 0.91,
              "brief_alignment": 0.88,
              "aesthetic_score": 0.9,
              "issues": [],
              "repair_hints": []
            }
            ```"""
        )

        self.assertFalse(report.hard_fail)
        self.assertGreaterEqual(report.score, 0.89)

    def test_nano_image_size_normalization_matches_laozhang_contract(self) -> None:
        self.assertEqual(NanoBananaService._normalize_size("1024"), "1K")
        self.assertEqual(NanoBananaService._normalize_size("1k"), "1K")
        self.assertEqual(NanoBananaService._normalize_size("2048"), "2K")
        self.assertEqual(NanoBananaService._normalize_size("4096"), "4K")
        self.assertEqual(NanoBananaService._normalize_size("weird"), "1K")

    def test_delivery_image_is_upscaled_to_4k_long_edge(self) -> None:
        image_bytes = _make_image_bytes((896, 1200), (220, 210, 205))

        processed, original_size, final_size = _prepare_delivery_image_sync(
            image_bytes,
            target_long_edge=4096,
        )

        self.assertEqual(original_size, (896, 1200))
        self.assertEqual(max(final_size), 4096)
        self.assertGreater(len(processed), 0)

    def test_nano_repair_prompt_preserves_identity_and_refs(self) -> None:
        prompt = assemble_nano_repair_prompt(
            render_prompt="A romantic Iceland wedding portrait at sunset.",
            repair_hints=["Soften the bride's expression", "Keep the groom gaze natural"],
            has_identity_refs=True,
            focus="emotional",
        )

        self.assertIn("current render that needs repair", prompt)
        self.assertIn("identity anchors only", prompt)
        self.assertIn("Original creative intent to preserve", prompt)
        self.assertIn("Improve facial expressions, gaze, and emotional warmth", prompt)

    def test_nano_repair_prompt_without_refs_keeps_photographic_intent(self) -> None:
        prompt = assemble_nano_repair_prompt(
            render_prompt="Studio bridal portrait with soft gold rim light.",
            repair_hints=["Correct the left hand anatomy"],
            has_identity_refs=False,
            focus="physical",
        )

        self.assertIn("input image is the current render", prompt)
        self.assertIn("Repair anatomy", prompt)
        self.assertIn("Do not add new props", prompt)

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
