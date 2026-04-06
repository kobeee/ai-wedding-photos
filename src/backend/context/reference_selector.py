"""参考图筛选 — 从用户上传中选出主图 + 辅图。

优先级策略：
- 有双人合照时：优先 `couple_full` + 新郎/新娘正脸图
- 无双人合照时：优先新郎/新娘正脸图，再补各自全身图
- 没有参考图时管线降级为"风格样片生成"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from utils.storage import read_upload_metadata

logger = logging.getLogger(__name__)

MAX_PRIMARY = 3
MAX_AUXILIARY = 2
MAX_TOTAL = MAX_PRIMARY + MAX_AUXILIARY
COUPLE_ANCHOR_TOTAL = 3
SINGLE_ROLE_PAIR_TOTAL = 4

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
    slot: str = ""
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
        counts = {"couple": 0, "bride": 0, "groom": 0, "unknown": 0}
        for ref in self.primary + self.auxiliary:
            counts[ref.role if ref.role in counts else "unknown"] += 1
        return counts

    @property
    def has_couple_identity(self) -> bool:
        counts = self.selected_role_counts
        return counts["bride"] > 0 and counts["groom"] > 0

    @property
    def has_couple_anchor(self) -> bool:
        counts = self.selected_role_counts
        return counts["couple"] > 0

    @property
    def couple_anchor(self) -> ReferenceImage | None:
        for ref in self.primary + self.auxiliary:
            if ref.role == "couple":
                return ref
        return None

    @property
    def structure_refs(self) -> list[tuple[bytes, str]]:
        """返回用于锁定双人比例/站位的结构参考。"""
        if self.couple_anchor is None:
            return []
        return [(self.couple_anchor.data, self.couple_anchor.mime)]

    @property
    def identity_refs(self) -> list[tuple[bytes, str]]:
        """返回纯身份参考，尽量排除双人结构锚，减少角色混淆。"""
        role_specific = [
            (ref.data, ref.mime)
            for ref in self.primary + self.auxiliary
            if ref.role in {"bride", "groom"}
        ]
        if role_specific:
            return role_specific
        return self.all_refs

    def identity_refs_for_role(self, role: str) -> list[tuple[bytes, str]]:
        refs = [
            (ref.data, ref.mime)
            for ref in self.primary + self.auxiliary
            if ref.role == role
        ]
        return refs


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


def _metadata_role(metadata: dict) -> str:
    role = str(metadata.get("role", "")).strip().lower()
    return role if role in {"couple", "bride", "groom"} else "unknown"


def _metadata_slot_bonus(slot: str) -> float:
    slot_bonus = {
        "couple_full": 0.18,
        "bride_portrait": 0.12,
        "groom_portrait": 0.12,
        "bride_full": 0.08,
        "groom_full": 0.08,
    }
    return slot_bonus.get(slot, 0.0)


def _metadata_is_accepted(metadata: dict) -> bool:
    validation = metadata.get("validation")
    if not isinstance(validation, dict):
        return True
    accepted = validation.get("accepted")
    return bool(accepted) if accepted is not None else True


def _choose_by_slot_preference(
    candidates: list[tuple[float, Path, bytes, str, str, str]],
    selected_paths: set[Path],
    preferred_slots: tuple[str, ...],
) -> tuple[float, Path, bytes, str, str, str] | None:
    available = [item for item in candidates if item[1] not in selected_paths]
    if not available:
        return None

    for slot in preferred_slots:
        for item in available:
            if item[5] == slot:
                return item

    return available[0]


def _append_reference(
    result_list: list[ReferenceImage],
    item: tuple[float, Path, bytes, str, str, str] | None,
    selected_paths: set[Path],
) -> None:
    if item is None:
        return

    _, fpath, data, mime, role, slot = item
    result_list.append(
        ReferenceImage(data=data, mime=mime, role=role, slot=slot, path=str(fpath)),
    )
    selected_paths.add(fpath)


def select_references(upload_dir: Path, *, gender: str = "couple") -> ReferenceSet:
    """从上传目录中筛选参考图。

    Args:
        upload_dir: 用户上传目录
        gender: "couple"/"female"/"male" — solo 场景只保留对应性别的参考图

    Returns:
        ReferenceSet with primary (1) + auxiliary (≤2) images.
    """
    result = ReferenceSet()

    if not upload_dir.exists():
        return result

    # solo 场景的角色过滤：排除异性参考图
    _excluded_roles: set[str] = set()
    if gender == "female":
        _excluded_roles = {"groom"}
    elif gender == "male":
        _excluded_roles = {"bride"}

    # 收集所有候选图
    candidates: list[tuple[float, Path, bytes, str, str, str]] = []
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
                metadata = read_upload_metadata(fpath)
                if not _metadata_is_accepted(metadata):
                    continue
                role = _metadata_role(metadata)
                # gender 过滤：solo 场景排除异性参考图
                if role in _excluded_roles:
                    continue
                slot = str(metadata.get("slot", "")).strip().lower()
                # solo 场景降权 couple 合照的 slot bonus（合照对 solo 价值较低）
                slot_bonus = _metadata_slot_bonus(slot)
                if gender != "couple" and slot == "couple_full":
                    slot_bonus *= 0.3
                candidates.append((score + slot_bonus, fpath, data, mime, role, slot))

    if not candidates:
        return result

    # 按质量分降序
    candidates.sort(key=lambda x: x[0], reverse=True)

    grouped: dict[str, list[tuple[float, Path, bytes, str, str, str]]] = {
        "couple": [],
        "bride": [],
        "groom": [],
        "unknown": [],
    }
    for item in candidates:
        grouped[item[4] if item[4] in grouped else "unknown"].append(item)

    selected_paths: set[Path] = set()

    target_total = MAX_TOTAL

    if grouped["couple"]:
        target_total = COUPLE_ANCHOR_TOTAL
        _append_reference(
            result.primary,
            _choose_by_slot_preference(grouped["couple"], selected_paths, ("couple_full",)),
            selected_paths,
        )
        for role in ("groom", "bride"):
            if len(result.primary) >= MAX_PRIMARY:
                break
            _append_reference(
                result.primary,
                _choose_by_slot_preference(
                    grouped[role],
                    selected_paths,
                    (f"{role}_portrait", f"{role}_full"),
                ),
                selected_paths,
            )
    elif grouped["bride"] and grouped["groom"]:
        target_total = SINGLE_ROLE_PAIR_TOTAL
        for role in ("groom", "bride"):
            _append_reference(
                result.primary,
                _choose_by_slot_preference(
                    grouped[role],
                    selected_paths,
                    (f"{role}_portrait", f"{role}_full"),
                ),
                selected_paths,
            )

        for role in ("groom", "bride"):
            if len(result.primary) + len(result.auxiliary) >= MAX_TOTAL:
                break
            _append_reference(
                result.auxiliary,
                _choose_by_slot_preference(
                    grouped[role],
                    selected_paths,
                    (f"{role}_full", f"{role}_portrait"),
                ),
                selected_paths,
            )
    else:
        _append_reference(result.primary, candidates[0], selected_paths)

    for _, fpath, data, mime, role, slot in candidates:
        if len(result.primary) + len(result.auxiliary) >= target_total:
            break
        if fpath in selected_paths:
            continue
        result.auxiliary.append(
            ReferenceImage(data=data, mime=mime, role=role, slot=slot, path=str(fpath)),
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
