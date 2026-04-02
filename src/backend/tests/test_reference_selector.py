from __future__ import annotations

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

from context.reference_selector import select_references


def _make_image_bytes(
    size: tuple[int, int],
    color: tuple[int, int, int],
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _write_upload(upload_dir: Path, name: str, slot: str, role: str, image_bytes: bytes) -> None:
    image_path = upload_dir / name
    image_path.write_bytes(image_bytes)
    image_path.with_suffix(image_path.suffix + ".meta.json").write_text(
        json.dumps(
            {
                "slot": slot,
                "role": role,
                "validation": {"accepted": True, "source": "test"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class ReferenceSelectorTests(unittest.TestCase):
    def test_couple_anchor_keeps_portraits_before_full_body_extras(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            _write_upload(
                upload_dir,
                "couple.jpg",
                "couple_full",
                "couple",
                _make_image_bytes((1800, 2400), (210, 180, 170)),
            )
            _write_upload(
                upload_dir,
                "groom-full.jpg",
                "groom_full",
                "groom",
                _make_image_bytes((2200, 3000), (180, 180, 210)),
            )
            _write_upload(
                upload_dir,
                "groom-portrait.jpg",
                "groom_portrait",
                "groom",
                _make_image_bytes((1000, 1400), (185, 185, 215)),
            )
            _write_upload(
                upload_dir,
                "bride-full.jpg",
                "bride_full",
                "bride",
                _make_image_bytes((2200, 3000), (225, 190, 200)),
            )
            _write_upload(
                upload_dir,
                "bride-portrait.jpg",
                "bride_portrait",
                "bride",
                _make_image_bytes((1000, 1400), (230, 195, 205)),
            )

            result = select_references(upload_dir)

            self.assertEqual(
                [ref.slot for ref in result.primary],
                ["couple_full", "groom_portrait", "bride_portrait"],
            )
            self.assertEqual(result.count, 3)


if __name__ == "__main__":
    unittest.main()
