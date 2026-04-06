from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.briefs import CreativeBrief, PromptVariant
from context.thresholds import passes_hero_identity_gate, passes_validation_track
from models.schemas import VerifiabilityAssessment
from services.production_orchestrator import _pick_validation_variant
from services.vlm_checker import VLMCheckerService


class VerificationArchitectureTests(unittest.TestCase):
    def test_parse_vlm_report_reads_verifiability_block(self) -> None:
        raw = """
        {
          "hard_fail": false,
          "identity_match": 0.91,
          "brief_alignment": 0.88,
          "aesthetic_score": 0.9,
          "verifiability": {
            "is_identity_verifiable": true,
            "is_proportion_verifiable": true,
            "face_area_ratio_bride": 0.041,
            "face_area_ratio_groom": 0.038,
            "body_visibility_score": 0.84,
            "notes": ["both faces readable"]
          },
          "issues": [],
          "repair_hints": []
        }
        """

        report = VLMCheckerService()._parse_report(raw)

        self.assertTrue(report.verifiability.is_identity_verifiable)
        self.assertTrue(report.verifiability.is_proportion_verifiable)
        self.assertAlmostEqual(report.verifiability.face_area_ratio_bride, 0.041)
        self.assertEqual(report.verifiability.notes, ["both faces readable"])

    def test_validation_track_requires_body_and_face_verifiability(self) -> None:
        # couple floor = 0.025, both faces must be >= 0.025
        strong = VerifiabilityAssessment(
            is_identity_verifiable=True,
            is_proportion_verifiable=True,
            face_area_ratio_bride=0.030,
            face_area_ratio_groom=0.028,
            body_visibility_score=0.81,
        )
        weak_face = VerifiabilityAssessment(
            is_identity_verifiable=True,
            is_proportion_verifiable=True,
            face_area_ratio_bride=0.012,
            face_area_ratio_groom=0.022,
            body_visibility_score=0.81,
        )

        self.assertTrue(passes_validation_track(strong, gender="couple"))
        self.assertFalse(passes_validation_track(weak_face, gender="couple"))

    def test_hero_gate_is_stricter_on_face_area(self) -> None:
        hero_ok = VerifiabilityAssessment(
            is_identity_verifiable=True,
            face_area_ratio_bride=0.041,
            face_area_ratio_groom=0.039,
        )
        hero_small_face = VerifiabilityAssessment(
            is_identity_verifiable=True,
            face_area_ratio_bride=0.021,
            face_area_ratio_groom=0.024,
        )

        self.assertTrue(passes_hero_identity_gate(hero_ok, gender="couple"))
        self.assertFalse(passes_hero_identity_gate(hero_small_face, gender="couple"))

    def test_pick_validation_variant_builds_custom_variant(self) -> None:
        brief = CreativeBrief(
            package_id="demo",
            story="demo",
            visual_essence="demo",
            emotion="demo",
            aesthetic="demo",
            variants=[
                PromptVariant(id="close", intent="close", framing="close", action="close"),
                PromptVariant(id="wide", intent="wide", framing="wide", action="wide"),
            ],
        )
        hero_variant = brief.variants[0]

        # Couple: medium-wide for identity verification
        couple_variant = _pick_validation_variant(brief, hero_variant, gender="couple")
        self.assertEqual(couple_variant.framing, "medium-wide")
        self.assertIn("_validation", couple_variant.id)
        self.assertIn("four eyes", couple_variant.action)

        # Solo: medium for waist-up portrait
        solo_variant = _pick_validation_variant(brief, hero_variant, gender="female")
        self.assertEqual(solo_variant.framing, "medium")
        self.assertIn("_validation", solo_variant.id)


if __name__ == "__main__":
    unittest.main()
