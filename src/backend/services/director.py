"""LLM 摄影导演服务 — 将套餐语义转化为 Camera Schema → 结构化渲染 Prompt。"""
from __future__ import annotations

import json
import logging

import httpx

from config import settings
from models.schemas import CameraSchema

logger = logging.getLogger(__name__)

# 套餐 → 场景语义映射（给 LLM 的上下文）
_PACKAGE_CONTEXT: dict[str, str] = {
    "iceland": "冰岛极光旅拍：黑沙滩、极光、冰川、瀑布，北欧冷冽浪漫",
    "french": "法式庄园：普罗旺斯薰衣草田、城堡花园、石桥、暖阳",
    "cyberpunk": "赛博朋克都市：霓虹灯、雨夜街道、全息投影、未来感",
    "minimal": "极简影棚：纯色背景、几何光影、高级灰调、杂志封面感",
    "onsen": "日式温泉：和风庭院、红叶、石灯笼、温泉蒸汽、侘寂美学",
    "starcamp": "星空露营：沙漠星空、帐篷灯串、篝火、银河、自由浪漫",
    # 兼容旧套餐 ID
    "chinese-classic": "中式经典：红色喜服、龙凤呈祥、中式庭院、红灯笼",
    "western-romantic": "西式浪漫：白色婚纱、教堂、玫瑰花束、金色阳光",
    "artistic-fantasy": "艺术幻想：梦幻森林、星月主题、水晶装饰、魔幻光影",
    "travel-destination": "旅拍风光：圣托里尼、海边悬崖、蓝白建筑、日落",
}

_MAKEUP_CONTEXT: dict[str, str] = {
    "natural": "素颜清透妆：轻薄底妆、裸色唇、自然眉形、清透感",
    "refined": "精致妆容：完美底妆、烟熏眼、玫瑰唇、高光修容",
    "sculpt": "骨相微调：全覆盖底妆、戏剧眼线、红唇、强修容、假睫毛",
}

_DIRECTOR_SYSTEM_PROMPT = """你是一位顶级婚纱摄影导演，擅长将抽象的风格需求转化为精确的摄影方案。

请根据用户提供的套餐风格和妆造偏好，输出一个 JSON 格式的 Camera Schema：

{
  "scene": "具体场景描述（英文，用于图像生成）",
  "lighting": "光线方案（英文）",
  "composition": "构图方式（英文）",
  "lens": "镜头参数（英文）",
  "mood": "情绪关键词（英文）",
  "wardrobe": "服装描述（英文）",
  "pose_direction": "姿势指导（英文）"
}

要求：
1. 所有值用英文，因为下游图像生成模型只接受英文 prompt
2. scene 要具体、有画面感，不要泛泛而谈
3. lighting 要专业，包含光源方向、色温、氛围
4. lens 要像真实摄影师一样指定焦段和光圈
5. wardrobe 要与场景风格匹配
6. pose_direction 要自然、有情感张力
7. 只输出 JSON，不要其他文字"""


class DirectorService:
    """LLM 摄影导演：套餐 + 妆造 → CameraSchema → 渲染 Prompt。"""

    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.laozhang_api_key}",
            "Content-Type": "application/json",
        }

    async def direct(
        self,
        package_id: str,
        makeup_style: str = "natural",
        gender: str = "female",
        preferences: dict | None = None,
    ) -> tuple[CameraSchema, str]:
        """
        LLM 摄影导演：套餐 → Camera Schema → 渲染 Prompt。
        返回 (CameraSchema, 最终渲染 prompt 字符串)。
        """
        if not settings.laozhang_api_key:
            return self._fallback(package_id, makeup_style, gender)

        scene_ctx = _PACKAGE_CONTEXT.get(package_id, _PACKAGE_CONTEXT["minimal"])
        makeup_ctx = _MAKEUP_CONTEXT.get(makeup_style, _MAKEUP_CONTEXT["natural"])

        user_msg = (
            f"套餐风格：{scene_ctx}\n"
            f"妆造风格：{makeup_ctx}\n"
            f"性别：{gender}\n"
        )
        if preferences:
            user_msg += f"用户额外偏好：{json.dumps(preferences, ensure_ascii=False)}\n"

        payload = {
            "model": settings.director_model,
            "messages": [
                {"role": "system", "content": _DIRECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 512,
            "temperature": 0.7,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            raw = data["choices"][0]["message"]["content"]
            schema = self._parse_schema(raw)
            prompt = self._schema_to_prompt(schema, gender)
            return schema, prompt

        except Exception:
            logger.exception("Director LLM call failed, using fallback")
            return self._fallback(package_id, makeup_style, gender)

    def _parse_schema(self, raw: str) -> CameraSchema:
        """解析 LLM 返回的 JSON。"""
        content = raw.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.strip().startswith("```") and not inside:
                    inside = True
                    continue
                if line.strip() == "```" and inside:
                    break
                if inside:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        result = json.loads(content)
        return CameraSchema(**result)

    def _schema_to_prompt(self, schema: CameraSchema, gender: str) -> str:
        """将 CameraSchema 渲染为图像生成 prompt。"""
        subject = "bride" if gender == "female" else "groom"
        return (
            f"Professional wedding photography. {schema.scene}. "
            f"Lighting: {schema.lighting}. "
            f"Composition: {schema.composition}. "
            f"Shot with {schema.lens}. "
            f"The {subject} wearing {schema.wardrobe}. "
            f"Pose: {schema.pose_direction}. "
            f"Mood: {schema.mood}. "
            f"Ultra-realistic, 8K, cinematic quality, no artifacts."
        )

    def _fallback(
        self, package_id: str, makeup_style: str, gender: str,
    ) -> tuple[CameraSchema, str]:
        """API 不可用时的硬编码 fallback。"""
        fallbacks: dict[str, CameraSchema] = {
            "iceland": CameraSchema(
                scene="Iceland black sand beach at sunset with northern lights",
                lighting="Golden hour side-backlight with aurora borealis glow",
                composition="Medium shot, rule of thirds, couple centered",
                lens="85mm f/1.4 shallow depth of field",
                mood="Romantic, ethereal, adventurous",
                wardrobe="Flowing white wedding gown with long train",
                pose_direction="Couple facing each other, foreheads touching gently",
            ),
            "french": CameraSchema(
                scene="Provence lavender field with stone chateau in background",
                lighting="Warm afternoon sun, soft diffused light through clouds",
                composition="Wide shot transitioning to medium, leading lines of lavender rows",
                lens="50mm f/1.8 natural perspective",
                mood="Warm, elegant, timeless",
                wardrobe="Classic A-line lace wedding dress with cathedral veil",
                pose_direction="Walking hand in hand through lavender, looking at each other",
            ),
            "cyberpunk": CameraSchema(
                scene="Neon-lit rainy city street with holographic billboards",
                lighting="Neon pink and cyan rim lighting, wet reflections",
                composition="Dutch angle, close-up with bokeh neon background",
                lens="35mm f/1.4 wide angle with lens flare",
                mood="Edgy, futuristic, passionate",
                wardrobe="Modern structured wedding outfit with metallic accents",
                pose_direction="Dramatic embrace under neon umbrella",
            ),
            "minimal": CameraSchema(
                scene="Pure white studio with geometric shadow patterns",
                lighting="Soft diffused studio light, single key light with fill",
                composition="Center frame, negative space, magazine cover style",
                lens="105mm f/2.0 portrait lens",
                mood="Clean, sophisticated, editorial",
                wardrobe="Minimalist silk slip dress, clean lines",
                pose_direction="Confident pose, direct gaze, subtle smile",
            ),
            "onsen": CameraSchema(
                scene="Japanese garden with autumn maple leaves and stone lanterns",
                lighting="Soft overcast light with warm tones, steam atmosphere",
                composition="Medium shot with foreground bokeh of maple leaves",
                lens="85mm f/1.4 with soft rendering",
                mood="Serene, intimate, wabi-sabi",
                wardrobe="White kimono-inspired wedding dress with obi sash",
                pose_direction="Gentle lean on partner's shoulder, eyes closed peacefully",
            ),
            "starcamp": CameraSchema(
                scene="Desert campsite under Milky Way with string lights and bonfire",
                lighting="Warm bonfire glow mixed with cool starlight, string light bokeh",
                composition="Wide establishing shot, couple small against vast sky",
                lens="24mm f/1.4 astrophotography wide angle",
                mood="Free-spirited, dreamy, adventurous",
                wardrobe="Bohemian lace dress with flower crown",
                pose_direction="Sitting by bonfire, wrapped in blanket, stargazing together",
            ),
        }

        # 兼容旧 ID
        alias = {
            "chinese-classic": "minimal",
            "western-romantic": "french",
            "artistic-fantasy": "cyberpunk",
            "travel-destination": "iceland",
        }
        key = alias.get(package_id, package_id)
        schema = fallbacks.get(key, fallbacks["minimal"])
        prompt = self._schema_to_prompt(schema, gender)
        return schema, prompt


director_service = DirectorService()