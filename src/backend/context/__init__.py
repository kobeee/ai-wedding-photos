"""上下文工程模块 — AI 婚纱摄影管线的认知框架与信息流。"""

from context.briefs import CreativeBrief, PromptVariant, get_brief
from context.prompt_assembler import assemble_generation_prompt
from context.reference_selector import select_references, ReferenceSet
from context.slot_renderer import render_slots, SlotPayload
from context.thresholds import decide_repair, RepairMode, DeliveryDecision
from context.variant_planner import get_variants

__all__ = [
    "CreativeBrief",
    "PromptVariant",
    "get_brief",
    "assemble_generation_prompt",
    "select_references",
    "ReferenceSet",
    "render_slots",
    "SlotPayload",
    "decide_repair",
    "RepairMode",
    "DeliveryDecision",
    "get_variants",
]
