from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from PIL import Image, ImageFilter

from config import settings

logger = logging.getLogger(__name__)


def _prepare_delivery_image_sync(
    image_data: bytes,
    *,
    target_long_edge: int,
) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
    with Image.open(BytesIO(image_data)) as image:
        source = image.convert("RGBA") if image.mode in ("RGBA", "LA") else image.convert("RGB")
        original_size = source.size
        width, height = original_size
        longest_edge = max(width, height)

        if longest_edge >= target_long_edge:
            output = BytesIO()
            source.save(output, format="PNG")
            return output.getvalue(), original_size, original_size

        scale = target_long_edge / max(longest_edge, 1)
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        resized = source.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        polished = resized.filter(ImageFilter.UnsharpMask(radius=1.6, percent=140, threshold=3))

        output = BytesIO()
        polished.save(output, format="PNG")
        return output.getvalue(), original_size, polished.size


async def prepare_delivery_image(image_data: bytes) -> bytes:
    processed, original_size, final_size = await asyncio.to_thread(
        _prepare_delivery_image_sync,
        image_data,
        target_long_edge=settings.delivery_long_edge,
    )
    logger.info(
        "Delivery image prepared: %s -> %s (target long edge=%d)",
        original_size,
        final_size,
        settings.delivery_long_edge,
    )
    return processed
