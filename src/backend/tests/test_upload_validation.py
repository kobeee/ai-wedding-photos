from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from main import app
from models.database import close_db
from services.upload_validator import (
    UploadBundleItem,
    UploadValidationIssue,
    UploadValidationReport,
    upload_validator_service,
)
from utils.storage import read_upload_metadata


def _make_image_bytes(
    size: tuple[int, int] = (1280, 1700),
    color: tuple[int, int, int] = (220, 200, 180),
    fmt: str = "JPEG",
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


class UploadValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        settings.db_path = str(base / "data" / "test.db")
        settings.upload_dir = str(base / "uploads")
        settings.output_dir = str(base / "outputs")
        settings.session_cookie_secure = False
        settings.laozhang_api_key = "test-chat-key"
        asyncio.run(close_db())

    def tearDown(self) -> None:
        asyncio.run(close_db())
        self.temp_dir.cleanup()

    def test_validator_schema_requires_mandatory_slots(self) -> None:
        errors = upload_validator_service.validate_slots_schema(
            [
                UploadBundleItem(
                    slot="groom_portrait",
                    role="groom",
                    filename="groom.jpg",
                    content=_make_image_bytes(),
                    mime_type="image/jpeg",
                )
            ]
        )

        self.assertTrue(any("缺少必传照片" in message for message in errors))

    def test_validator_heuristic_accepts_complete_bundle(self) -> None:
        report = upload_validator_service._heuristic_validate(
            [
                UploadBundleItem("groom_portrait", "groom", "g1.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("groom_full", "groom", "g2.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("bride_portrait", "bride", "b1.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("bride_full", "bride", "b2.jpg", _make_image_bytes(), "image/jpeg"),
            ]
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.errors, [])

    def test_ai_validation_selection_skips_optional_couple_when_budget_is_full(self) -> None:
        selected = upload_validator_service._select_items_for_ai_validation(
            [
                UploadBundleItem("groom_portrait", "groom", "g1.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("groom_full", "groom", "g2.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("bride_portrait", "bride", "b1.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("bride_full", "bride", "b2.jpg", _make_image_bytes(), "image/jpeg"),
                UploadBundleItem("couple_full", "couple", "c1.jpg", _make_image_bytes(), "image/jpeg"),
            ]
        )

        self.assertEqual(len(selected), 4)
        self.assertEqual(
            [item.slot for item, _prepared, _mime in selected],
            ["groom_portrait", "bride_portrait", "groom_full", "bride_full"],
        )

    def test_ai_validation_parse_json_tolerates_fenced_wrapper(self) -> None:
        payload = """```json
        {
          "slot_checks": {"groom_portrait": "pass"},
          "identity_checks": {"groom_pair_same_person": "pass"}
        }
        ```"""

        parsed = upload_validator_service._parse_json(payload)

        self.assertEqual(parsed["slot_checks"]["groom_portrait"], "pass")

    def test_upload_route_persists_slot_metadata(self) -> None:
        validation_report = UploadValidationReport(
            ok=True,
            issues=[],
            slot_messages={"groom_portrait": "通过"},
            source="ai",
        )
        validate_mock = AsyncMock(return_value=validation_report)

        with (
            patch("routers.upload.upload_validator_service.validate", new=validate_mock),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("groom-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "bride")),
                    ("roles", (None, "bride")),
                    ("slots", (None, "groom_portrait")),
                    ("slots", (None, "groom_full")),
                    ("slots", (None, "bride_portrait")),
                    ("slots", (None, "bride_full")),
                ],
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(validate_mock.await_count, 1)
            payload = response.json()
            self.assertEqual(payload["files"][0]["slot"], "groom_portrait")
            saved_path = (
                Path(settings.upload_dir)
                / payload["user_id"]
                / Path(payload["files"][0]["url"]).name
            )
            metadata = read_upload_metadata(saved_path)
            self.assertEqual(metadata.get("slot"), "groom_portrait")
            self.assertEqual(metadata.get("role"), "groom")
            self.assertTrue(metadata.get("validation", {}).get("accepted"))

    def test_upload_route_allows_single_slot_without_bundle_validation(self) -> None:
        validate_mock = AsyncMock()

        with (
            patch("routers.upload.upload_validator_service.validate", new=validate_mock),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom.jpg", _make_image_bytes(), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("slots", (None, "groom_portrait")),
                ],
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(validate_mock.await_count, 0)
            payload = response.json()
            first_file = payload["files"][0]
            self.assertEqual(first_file["slot"], "groom_portrait")
            saved_path = Path(settings.upload_dir) / payload["user_id"] / Path(first_file["url"]).name
            metadata = read_upload_metadata(saved_path)
            self.assertEqual(metadata.get("slot"), "groom_portrait")
            self.assertEqual(metadata.get("role"), "groom")
            self.assertTrue(metadata.get("validation", {}).get("accepted"))

    def test_upload_route_keeps_original_bytes_and_extension(self) -> None:
        original_png = _make_image_bytes(size=(900, 1200), color=(120, 160, 210), fmt="PNG")
        validation_report = UploadValidationReport(ok=True, issues=[], slot_messages={}, source="ai")

        with (
            patch("routers.upload.upload_validator_service.validate", new=AsyncMock(return_value=validation_report)),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom.png", original_png, "image/png")),
                    ("files", ("groom-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "bride")),
                    ("roles", (None, "bride")),
                    ("slots", (None, "groom_portrait")),
                    ("slots", (None, "groom_full")),
                    ("slots", (None, "bride_portrait")),
                    ("slots", (None, "bride_full")),
                ],
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            first_file = payload["files"][0]
            saved_path = Path(settings.upload_dir) / payload["user_id"] / Path(first_file["url"]).name
            self.assertEqual(saved_path.suffix.lower(), ".png")
            self.assertEqual(saved_path.read_bytes(), original_png)

    def test_upload_route_replaces_existing_slot_file(self) -> None:
        with TestClient(app) as client:
            first_response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom-a.jpg", _make_image_bytes(color=(120, 120, 120)), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("slots", (None, "groom_portrait")),
                ],
            )
            self.assertEqual(first_response.status_code, 200)
            payload = first_response.json()
            user_dir = Path(settings.upload_dir) / payload["user_id"]

            second_response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom-b.jpg", _make_image_bytes(color=(220, 180, 180)), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("slots", (None, "groom_portrait")),
                ],
            )
            self.assertEqual(second_response.status_code, 200)

            saved_images = sorted(path for path in user_dir.iterdir() if path.is_file() and not path.name.endswith(".meta.json"))
            self.assertEqual(len(saved_images), 1)
            metadata = read_upload_metadata(saved_images[0])
            self.assertEqual(metadata.get("slot"), "groom_portrait")
            self.assertEqual(metadata.get("original_filename"), "groom-b.jpg")

    def test_upload_route_blocks_when_validation_fails(self) -> None:
        validation_report = UploadValidationReport(
            ok=False,
            issues=[UploadValidationIssue("error", "新郎全身不是同一个人", "groom_full")],
            source="ai",
        )

        with (
            patch("routers.upload.upload_validator_service.validate", new=AsyncMock(return_value=validation_report)),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/upload",
                files=[
                    ("files", ("groom.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("groom-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride.jpg", _make_image_bytes(), "image/jpeg")),
                    ("files", ("bride-full.jpg", _make_image_bytes(), "image/jpeg")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "groom")),
                    ("roles", (None, "bride")),
                    ("roles", (None, "bride")),
                    ("slots", (None, "groom_portrait")),
                    ("slots", (None, "groom_full")),
                    ("slots", (None, "bride_portrait")),
                    ("slots", (None, "bride_full")),
                ],
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("新郎全身不是同一个人", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
