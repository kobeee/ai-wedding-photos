"""参考图筛选 — 从用户上传中选出主图 + 辅图。

规则（来自工程落地版 §五）：
- 主身份锚图：1 张（正脸清晰、遮挡最少、表情自然）
- 辅助锚图：最多 2 张（不同角度或半身/全身）
- 总上限：3 张
- 没有参考图时管线降级为"风格样片生成"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from utils.storage import upload_metadata_path

logger = logging.getLogger(__name__)

MAX_PRIMARY = 1
MAX_AUXILIARY = 2
MAX_TOTAL = MAX_PRIMARY + MAX_AUXILIARY

# 最小可接受尺寸（像素，短边）
MIN_SHORT_SIDE = 256
# 最小可接受文件大小（bytes），过小的图可能是缩略图
MIN_FILE_SIZE = 20 * 1024  # 20KB


@dataclass
class ReferenceImage:
    """单张参考图及其角色元数据。"""

    data: bytes
    mime: str
    role: str = "unknown"
    path: str = ""


@dataclass
class ReferenceSet:
    """筛选后的参考图集合。"""

    primary: list[ReferenceImage] = field(default_factory=list)
    auxiliary: list[ReferenceImage] = field(default_factory=list)

    @property
    def all_refs(self) -> list[tuple[bytes, str]]:
        return [(ref.data, ref.mime) for ref in self.primary + self.auxiliary]

    @property
    def has_identity(self) -> bool:
        """是否有有效的身份参考。"""
        return len(self.primary) > 0

    @property
    def count(self) -> int:
        return len(self.primary) + len(self.auxiliary)

    @property
    def selected_role_counts(self) -> dict[str, int]:
        counts = {"bride": 0, "groom": 0, "unknown": 0}
        for ref in self.primary + self.auxiliary:
            counts[ref.role if ref.role in counts else "unknown"] += 1
        return counts

    @property
    def has_couple_identity(self) -> bool:
        counts = self.selected_role_counts
        return counts["bride"] > 0 and counts["groom"] > 0


def _image_quality_score(data: bytes) -> float:
    """粗略评估图片质量，返回 0-1 分。

    优先级：尺寸大 > 文件大 > 横竖比接近 3:4。
    不做人脸检测（避免引入重依赖），靠尺寸和文件体积做粗筛。
    """
    score = 0.0

    # 文件大小分（越大越可能是高清正片）
    size_kb = len(data) / 1024
    if size_kb >= 500:
        score += 0.4
    elif size_kb >= 100:
        score += 0.2
    elif size_kb < MIN_FILE_SIZE / 1024:
        return 0.0  # 太小，可能是缩略图

    # 像素尺寸分
    try:
        from io import BytesIO

        img = Image.open(BytesIO(data))
        w, h = img.size
        short_side = min(w, h)

        if short_side < MIN_SHORT_SIDE:
            return 0.0  # 太小不可用

        if short_side >= 1024:
            score += 0.4
        elif short_side >= 512:
            score += 0.2
        else:
            score += 0.1

        # 竖版加分（婚纱照常见 3:4 或 2:3）
        ratio = max(w, h) / max(min(w, h), 1)
        if 1.2 <= ratio <= 1.6:
            score += 0.2
        elif ratio <= 1.1:
            # 方形，也不错
            score += 0.1
    except Exception:
        # 图片损坏或无法解析
        logger.warning("Failed to parse image for quality scoring")
        score += 0.1

    return min(score, 1.0)


def _load_role(image_path: Path) -> str:
    """从 sidecar 元数据中读取角色标签。"""
    meta_path = upload_metadata_path(image_path)
    if not meta_path.exists():
        return "unknown"

    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read upload metadata: %s", meta_path)
        return "unknown"

    role = str(raw.get("role", "")).strip().lower()
    if role in {"bride", "groom"}:
        return role
    return "unknown"


def select_references(upload_dir: Path) -> ReferenceSet:
    """从上传目录中筛选参考图。

    Returns:
        ReferenceSet with primary (1) + auxiliary (≤2) images.
    """
    result = ReferenceSet()

    if not upload_dir.exists():
        return result

    # 收集所有候选图
    candidates: list[tuple[float, Path, bytes, str, str]] = []
    for ext_pattern in ("*.jpg", "*.jpeg", "*.png"):
        for fpath in upload_dir.glob(ext_pattern):
            if fpath.name.endswith(".meta.json"):
                continue
            try:
                data = fpath.read_bytes()
            except OSError:
                continue

            mime = "image/png" if fpath.suffix.lower() == ".png" else "image/jpeg"
            score = _image_quality_score(data)
            if score > 0:
                role = _load_role(fpath)
                candidates.append((score, fpath, data, mime, role))

    if not candidates:
        return result

    # 按质量分降序
    candidates.sort(key=lambda x: x[0], reverse=True)

    grouped: dict[str, list[tuple[float, Path, bytes, str, str]]] = {
        "bride": [],
        "groom": [],
        "unknown": [],
    }
    for item in candidates:
        grouped[item[4] if item[4] in grouped else "unknown"].append(item)

    selected_paths: set[Path] = set()

    # couple 模式：优先保证新郎/新娘各至少一张。
    if grouped["bride"] and grouped["groom"]:
        for role in ("bride", "groom"):
            _, fpath, data, mime, _ = grouped[role][0]
            result.primary.append(
                ReferenceImage(data=data, mime=mime, role=role, path=str(fpath)),
            )
            selected_paths.add(fpath)
    else:
        _, fpath, data, mime, role = candidates[0]
        result.primary.append(
            ReferenceImage(data=data, mime=mime, role=role, path=str(fpath)),
        )
        selected_paths.add(fpath)

    for _, fpath, data, mime, role in candidates:
        if len(result.primary) + len(result.auxiliary) >= MAX_TOTAL:
            break
        if fpath in selected_paths:
            continue
        result.auxiliary.append(
            ReferenceImage(data=data, mime=mime, role=role, path=str(fpath)),
        )
        selected_paths.add(fpath)

    logger.info(
        "Reference selection: %d primary, %d auxiliary from %d candidates (roles=%s)",
        len(result.primary),
        len(result.auxiliary),
        len(candidates),
        result.selected_role_counts,
    )

    return result
