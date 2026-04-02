from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from main import app
from models.database import close_db, update_order


def _make_image_bytes(size: tuple[int, int] = (1200, 1600), color: tuple[int, int, int] = (220, 200, 180)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class OrderClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        settings.db_path = str(base / "data" / "test.db")
        settings.upload_dir = str(base / "uploads")
        settings.output_dir = str(base / "outputs")
        settings.session_cookie_secure = False
        settings.laozhang_nano_api_key = "test-nano-key"
        settings.laozhang_api_key = "test-chat-key"
        asyncio.run(close_db())

    def tearDown(self) -> None:
        asyncio.run(close_db())
        self.temp_dir.cleanup()

    def test_paid_order_payment_and_delivery_flow(self) -> None:
        fake_report = SimpleNamespace(
            score=0.96,
            inspection_unavailable=False,
            hard_fail=False,
            identity_match=0.98,
            brief_alignment=0.96,
            aesthetic_score=0.95,
            physical_issues=[],
            emotional_issues=[],
            repair_hints=[],
            issues=[],
        )
        fake_image = _make_image_bytes()

        with (
            patch("routers.makeup.nano_banana_service.image_to_image", new=AsyncMock(return_value=fake_image)),
            patch("routers.makeup.nano_banana_service.text_to_image", new=AsyncMock(return_value=fake_image)),
            patch("routers.generate.nano_banana_service.multi_reference_generate", new=AsyncMock(return_value=fake_image)),
            patch("routers.generate.nano_banana_service.text_to_image", new=AsyncMock(return_value=fake_image)),
            patch("routers.generate.nano_banana_service.repair_with_references", new=AsyncMock(return_value=fake_image)),
            patch("routers.generate.vlm_checker_service.check_and_suggest_fix_prompt", new=AsyncMock(return_value=(fake_report, ""))),
            patch("routers.generate.director_service.edit_brief", new=AsyncMock(side_effect=lambda brief, _prefs: brief)),
        ):
            with TestClient(app) as client:
                upload_response = client.post(
                    "/api/upload",
                    files=[
                        ("files", ("groom.png", fake_image, "image/png")),
                        ("files", ("bride.png", fake_image, "image/png")),
                        ("roles", (None, "groom")),
                        ("roles", (None, "bride")),
                    ],
                )
                self.assertEqual(upload_response.status_code, 200)
                user_id = upload_response.json()["user_id"]

                makeup_response = client.post(
                    "/api/makeup/generate",
                    json={
                        "user_id": user_id,
                        "gender": "female",
                        "style": "natural",
                    },
                )
                self.assertEqual(makeup_response.status_code, 200)
                self.assertEqual(len(makeup_response.json()["images"]), 3)

                skus_response = client.get("/api/skus")
                self.assertEqual(skus_response.status_code, 200)
                self.assertGreaterEqual(len(skus_response.json()), 1)

                order_response = client.post(
                    "/api/orders",
                    json={
                        "package_id": "iceland",
                        "sku_id": "starter_399",
                    },
                )
                self.assertEqual(order_response.status_code, 200)
                order_id = order_response.json()["order_id"]

                asyncio.run(
                    update_order(
                        order_id,
                        entitlement_snapshot={
                            "promised_photos": 2,
                            "scene_count": 1,
                            "photo_mix": {"couple": 2},
                            "rerun_quota": 1,
                            "repaint_quota": 0,
                            "retention_days": 30,
                            "delivery_specs": ["4k"],
                            "preview_policy": "full",
                        },
                    ),
                )

                blocked_start = client.post(
                    f"/api/orders/{order_id}/start",
                    json={
                        "groom_style": "natural clean grooming",
                        "bride_style": "refined elegant bridal makeup",
                    },
                )
                self.assertEqual(blocked_start.status_code, 409)

                payment_create = client.post(
                    "/api/pay/mock/create",
                    json={"order_id": order_id},
                )
                self.assertEqual(payment_create.status_code, 200)
                payment_id = payment_create.json()["payment_id"]

                payment_confirm = client.post(
                    "/api/pay/mock/confirm",
                    json={"payment_id": payment_id, "succeed": True},
                )
                self.assertEqual(payment_confirm.status_code, 200)
                self.assertEqual(payment_confirm.json()["payment_status"], "paid")

                start_response = client.post(
                    f"/api/orders/{order_id}/start",
                    json={
                        "groom_style": "natural clean grooming",
                        "bride_style": "refined elegant bridal makeup",
                    },
                )
                self.assertEqual(start_response.status_code, 200)

                order_after = client.get(f"/api/orders/{order_id}")
                self.assertEqual(order_after.status_code, 200)
                self.assertIn(order_after.json()["fulfillment_status"], {"delivered", "partially_delivered"})
                self.assertEqual(order_after.json()["deliverable_count"], 2)

                deliverables = client.get(f"/api/orders/{order_id}/deliverables")
                self.assertEqual(deliverables.status_code, 200)
                items = deliverables.json()["items"]
                self.assertEqual(len(items), 2)

                file_response = client.get(items[0]["url"])
                self.assertEqual(file_response.status_code, 200)
                self.assertGreater(len(file_response.content), 0)
                self.assertIn("no-store", file_response.headers.get("cache-control", ""))

                rerun_response = client.post(
                    f"/api/orders/{order_id}/reruns",
                    json={
                        "groom_style": "natural clean grooming",
                        "bride_style": "refined elegant bridal makeup",
                    },
                )
                self.assertEqual(rerun_response.status_code, 200)

    def test_makeup_route_reuses_cached_previews_for_same_reference(self) -> None:
        fake_image = _make_image_bytes()
        image_to_image = AsyncMock(return_value=fake_image)

        with (
            patch("routers.makeup.nano_banana_service.image_to_image", new=image_to_image),
            patch("routers.makeup.nano_banana_service.text_to_image", new=AsyncMock(return_value=fake_image)),
            TestClient(app) as client,
        ):
            upload_response = client.post(
                "/api/upload",
                files=[
                    ("files", ("bride.png", fake_image, "image/png")),
                    ("roles", (None, "bride")),
                    ("slots", (None, "bride_portrait")),
                ],
            )
            self.assertEqual(upload_response.status_code, 200)
            user_id = upload_response.json()["user_id"]

            first_response = client.post(
                "/api/makeup/generate",
                json={
                    "user_id": user_id,
                    "gender": "female",
                    "style": "natural",
                },
            )
            self.assertEqual(first_response.status_code, 200)
            self.assertEqual(len(first_response.json()["images"]), 3)
            self.assertTrue(all("?v=" in image_url for image_url in first_response.json()["images"]))

            second_response = client.post(
                "/api/makeup/generate",
                json={
                    "user_id": user_id,
                    "gender": "female",
                    "style": "natural",
                },
            )
            self.assertEqual(second_response.status_code, 200)
            self.assertEqual(second_response.json()["images"], first_response.json()["images"])
            self.assertEqual(image_to_image.await_count, 3)


if __name__ == "__main__":
    unittest.main()
