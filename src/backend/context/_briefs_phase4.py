"""Phase 4 套餐 Brief 模板 — 8 个新套餐。

合并方式：将下方变量和 _BRIEFS_PHASE4 字典 merge 到 briefs.py 的 _BRIEFS 中。
"""

from context.briefs import CreativeBrief, PromptVariant


# ---------------------------------------------------------------------------
# 1. french — 法式庄园
# ---------------------------------------------------------------------------

_BRIEF_FRENCH = CreativeBrief(
    package_id="french",
    story="An afternoon that tastes of lavender, old stone, and slow-burning devotion.",
    visual_essence=(
        "Provençal lavender fields bleeding into a limestone château garden. "
        "Late golden-hour light rakes through centuries-old plane trees, casting "
        "long honeyed shadows on gravel paths. Every surface carries texture — "
        "crumbling plaster, wrought iron, sun-warmed skin."
    ),
    emotion="Unhurried elegance — love that has nowhere else to be",
    aesthetic="Warm amber and dusty violet palette, painterly soft focus on edges, linen texture, golden film grain",
    wardrobe_bride="Romantic A-line gown in ivory silk with delicate lace sleeves, straw hat optional",
    wardrobe_groom="Relaxed taupe linen suit, open collar, rolled sleeves, leather loafers",
    makeup_default="Sun-kissed flush, dewy skin with freckles visible, berry-stained lip, effortless brows",
    avoid_global=[
        "saturated neon tones",
        "modern glass architecture",
        "harsh midday shadows",
        "over-retouched porcelain skin",
        "extra fingers or limbs",
        "lavender that looks plastic or CGI",
        "tourist crowds in background",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="natural",
    variants=[
        PromptVariant(
            id="french_lavender",
            intent="Drowning in purple — two people lost in an endless field",
            framing="wide",
            action="Walking hand-in-hand through chest-high lavender rows, her free hand trailing the blossoms",
            emotion_focus="Intoxicating calm — the scent itself is visible in the light",
            avoid_local=["flat lavender color", "stiff walking pose", "empty sky"],
        ),
        PromptVariant(
            id="french_courtyard",
            intent="A stolen kiss behind the château wall",
            framing="medium",
            action="Leaning against a weathered stone wall, his hand on her waist, foreheads close, smiling",
            emotion_focus="Private warmth — the wall has kept secrets for 300 years, theirs is the sweetest",
            avoid_local=["modern elements in wall", "harsh directional light", "awkward lean angles"],
        ),
        PromptVariant(
            id="french_bridge",
            intent="Time stands still on the old stone bridge",
            framing="medium",
            action="Standing on a mossy arched stone bridge, her veil caught in a breeze, river below reflecting gold",
            emotion_focus="Fairy-tale permanence — this bridge was here before them and will remain after",
            avoid_local=["CGI water", "veil covering face", "modern bridge railing"],
        ),
        PromptVariant(
            id="french_golden",
            intent="The last light of a Provençal afternoon",
            framing="close",
            action="Golden backlight streaming through her hair, his lips near her temple, eyes closed together",
            emotion_focus="Gratitude — this is the day they will remember when they are eighty",
            avoid_local=["blown-out highlights", "lens flare obscuring faces", "unnatural hair glow"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 2. minimal — 极简影棚
# ---------------------------------------------------------------------------

_BRIEF_MINIMAL = CreativeBrief(
    package_id="minimal",
    story="When everything else is stripped away, only they remain.",
    visual_essence=(
        "A controlled studio environment — seamless paper backdrop in dove grey or warm white. "
        "Geometric light shafts cut across the frame like Brutalist architecture. "
        "The couple IS the composition; negative space does all the talking."
    ),
    emotion="Refined intensity — every glance is amplified by silence",
    aesthetic="High-fashion editorial, advanced grey tones with selective warm highlights on skin, razor-sharp focus, zero clutter",
    wardrobe_bride="Minimalist column gown in matte crepe, clean neckline, sculptural simplicity",
    wardrobe_groom="Perfectly tailored charcoal suit, black turtleneck, no accessories",
    makeup_default="Flawless matte skin, sculpted cheekbones, nude lip, strong defined brow",
    avoid_global=[
        "busy backgrounds",
        "visible studio equipment",
        "colorful props",
        "heavy vignetting",
        "extra fingers or limbs",
        "overly dramatic expressions",
        "wrinkled backdrop paper",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="high_contrast",
    pose_energy="still",
    variants=[
        PromptVariant(
            id="minimal_silhouette",
            intent="Two shapes becoming one in the negative space",
            framing="wide",
            action="Full-body silhouette against a bright seamless backdrop, bodies close but not touching, tension in the gap",
            emotion_focus="Magnetic pull — the space between them is charged",
            avoid_local=["muddy silhouette edges", "visible floor seam", "flat grey-on-grey"],
        ),
        PromptVariant(
            id="minimal_hands",
            intent="The whole story told by two hands",
            framing="close",
            action="Extreme close-up of intertwined hands against grey fabric, wedding rings catching a single shaft of light",
            emotion_focus="Quiet permanence — no grand gesture, just the grip that says everything",
            avoid_local=["extra fingers", "distorted ring proportions", "blurry focus"],
        ),
        PromptVariant(
            id="minimal_editorial",
            intent="Magazine cover — they own the camera",
            framing="medium",
            action="Standing shoulder-to-shoulder facing camera, direct eye contact, geometric light stripe across both faces",
            emotion_focus="Confident intimacy — no performance, just presence",
            avoid_local=["asymmetric light stripe", "dead eyes", "stiff posture"],
        ),
        PromptVariant(
            id="minimal_movement",
            intent="Controlled chaos in a controlled space",
            framing="wide",
            action="Mid-turn, her gown creating a sculptural sweep, his hand steadying her waist, motion blur only on fabric edges",
            emotion_focus="Joy breaking through restraint — they forgot the camera for a second",
            avoid_local=["excessive motion blur", "lost facial detail", "fabric looking frozen"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 3. onsen — 日式温泉
# ---------------------------------------------------------------------------

_BRIEF_ONSEN = CreativeBrief(
    package_id="onsen",
    story="Beauty in impermanence — two lives meeting where the maples fall.",
    visual_essence=(
        "A traditional ryokan garden in peak momiji season. Crimson and amber leaves "
        "drift onto moss-covered stone lanterns and still water. Steam from a hidden "
        "onsen curls through the cold air. Wabi-sabi everywhere — cracked stone, "
        "weathered wood, asymmetric beauty."
    ),
    emotion="Wabi-sabi tenderness — finding perfection in the fleeting",
    aesthetic="Muted earth tones with crimson accents, soft diffused light, misty atmosphere, Japanese woodblock print sensibility",
    wardrobe_bride="White uchikake kimono with subtle crane or wave embroidery, or modern white furisode",
    wardrobe_groom="Dark indigo or charcoal montsuki haori hakama, traditional and sharp",
    makeup_default="Porcelain luminous skin, soft gradient lip in plum, minimal eye makeup, natural brow",
    avoid_global=[
        "cherry blossom cliché overdose",
        "geisha costume stereotyping",
        "neon signage",
        "modern architecture",
        "extra fingers or limbs",
        "anime-style facial features",
        "overly saturated red leaves",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="still",
    variants=[
        PromptVariant(
            id="onsen_garden",
            intent="Two souls in a garden that has been meditating for centuries",
            framing="wide",
            action="Walking along a mossy stone path under a canopy of red maples, her kimono trailing on wet stone",
            emotion_focus="Reverent stillness — even the leaves fall slowly here",
            avoid_local=["cluttered garden", "unrealistic leaf density", "stiff walking"],
        ),
        PromptVariant(
            id="onsen_lantern",
            intent="Old light, new love",
            framing="medium",
            action="Standing beside a weathered stone lantern at dusk, warm lantern glow on their faces, steam rising behind",
            emotion_focus="Ancient warmth — the lantern has witnessed countless seasons, but never this",
            avoid_local=["overly bright lantern", "lost steam detail", "modern lighting fixtures"],
        ),
        PromptVariant(
            id="onsen_bridge",
            intent="The red bridge between two lives",
            framing="medium",
            action="Paused on a vermillion arched bridge over a koi pond, leaning together, maple leaves falling around them",
            emotion_focus="Transition — crossing from one life into another, together",
            avoid_local=["CGI koi fish", "plastic-looking bridge", "unnatural leaf placement"],
        ),
        PromptVariant(
            id="onsen_intimate",
            intent="Warmth in the cold — steam and skin",
            framing="close",
            action="Sitting on engawa veranda edge, wrapped in matching yukata, tea cups between them, steam mingling with breath",
            emotion_focus="Domestic intimacy — the quiet after the ceremony, before the world rushes back",
            avoid_local=["visible modern items", "harsh shadows on face", "cultural inaccuracies in yukata"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 4. starcamp — 星空露营
# ---------------------------------------------------------------------------

_BRIEF_STARCAMP = CreativeBrief(
    package_id="starcamp",
    story="They pitched a tent at the edge of the galaxy and called it home.",
    visual_essence=(
        "Desert plateau under a crystalline Milky Way. A canvas bell tent glows amber "
        "from within, fairy lights strung between cacti. A dying campfire throws warm "
        "embers into the cold air. The couple is the only sign of human life "
        "for a hundred miles."
    ),
    emotion="Wild freedom — love untamed by walls or ceilings",
    aesthetic="Deep indigo sky gradient to warm amber ground, bioluminescent fairy-light bokeh, long-exposure star trails optional, earthy warmth",
    wardrobe_bride="Bohemian flowing dress in cream or champagne, barefoot, wildflower crown optional",
    wardrobe_groom="Relaxed earth-tone shirt, suspenders, rolled-up sleeves, boots",
    makeup_default="Warm bronzed glow, sun-kissed cheeks, nude lip, loose natural hair",
    avoid_global=[
        "light pollution glow on horizon",
        "plastic camping gear",
        "daytime sky",
        "overcrowded campsite",
        "extra fingers or limbs",
        "noise-artifact stars",
        "glamping influencer aesthetic",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="playful",
    variants=[
        PromptVariant(
            id="star_milkyway",
            intent="Two specks of warmth under an infinite sky",
            framing="wide",
            action="Standing together on a rock outcrop, Milky Way arching overhead, silhouettes backlit by tent glow",
            emotion_focus="Humbling vastness — they are small, but their gravity is immense",
            avoid_local=["noisy star field", "lost figure detail", "flat sky gradient"],
        ),
        PromptVariant(
            id="star_campfire",
            intent="The oldest light and the newest love",
            framing="medium",
            action="Sitting on a blanket by the campfire, her head on his shoulder, sparks rising into the dark",
            emotion_focus="Primal comfort — fire, warmth, each other, nothing else needed",
            avoid_local=["overblown fire highlights", "harsh orange cast on skin", "stiff sitting pose"],
        ),
        PromptVariant(
            id="star_fairylights",
            intent="A constellation they built themselves",
            framing="medium",
            action="Dancing slowly under a canopy of string lights between desert plants, barefoot on warm sand",
            emotion_focus="Homemade magic — they don't need a ballroom",
            avoid_local=["tangled visible wires", "overexposed lights", "cold color temperature"],
        ),
        PromptVariant(
            id="star_dawn",
            intent="The first light of everything",
            framing="wide",
            action="Wrapped in a blanket together at tent entrance, watching the first blue-pink glow on the horizon, coffee in hand",
            emotion_focus="New beginning — the night was theirs, and so is the morning",
            avoid_local=["harsh sunrise glare", "lost blanket texture", "empty expressions"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 5. chinese-classic — 中式经典
# ---------------------------------------------------------------------------

_BRIEF_CHINESE_CLASSIC = CreativeBrief(
    package_id="chinese-classic",
    story="A thousand years of ceremony, and tonight it breathes for them alone.",
    visual_essence=(
        "A grand Chinese courtyard at golden hour — red lacquer pillars, stone lions, "
        "crimson lanterns glowing like small suns. The bride's phoenix crown catches the light "
        "as red silk billows in the breeze. Every detail is intentional, every symmetry "
        "is ancestral, every color carries meaning."
    ),
    emotion="Ceremonial grandeur — the weight of heritage and the lightness of new love",
    aesthetic="Vermillion and gold dominant, lacquer sheen, deep shadow contrast, imperial richness without heaviness",
    wardrobe_bride="Red xiuhe or qipao with gold phoenix embroidery, phoenix crown or red veil, gold jewelry",
    wardrobe_groom="Red or dark changshan with gold dragon embroidery, matching groom cap, gold waist sash",
    makeup_default="Flawless porcelain base, classic red lip, winged liner, blush placed high, defined brows",
    avoid_global=[
        "cheap satin fabric look",
        "culturally inaccurate costume details",
        "western church elements",
        "modern buildings visible",
        "extra fingers or limbs",
        "generic Chinese restaurant aesthetic",
        "plastic lantern look",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="tender",
    variants=[
        PromptVariant(
            id="chinese_courtyard",
            intent="The courtyard has waited a century for this couple",
            framing="wide",
            action="Walking through a moon gate into a lantern-lit courtyard, red silk trailing behind her",
            emotion_focus="Timeless arrival — as if the architecture itself exhales in relief",
            avoid_local=["flat courtyard perspective", "lost embroidery detail", "dead lanterns"],
        ),
        PromptVariant(
            id="chinese_veil",
            intent="The moment before the world changes",
            framing="close",
            action="He lifts the red veil with a gold ruyi scepter, her eyes meeting his for the first time as husband and wife",
            emotion_focus="Sacred revelation — a thousand years of tradition distilled into one glance",
            avoid_local=["veil obscuring both faces", "inaccurate ruyi design", "harsh flash look"],
        ),
        PromptVariant(
            id="chinese_lanterns",
            intent="Red lanterns and redder promises",
            framing="medium",
            action="Standing beneath a corridor of hanging red lanterns, faces lit warm from below, hands clasped",
            emotion_focus="Warm gravity — the lanterns glow brighter because they are here",
            avoid_local=["uniform boring lantern grid", "underlit faces", "flat perspective"],
        ),
        PromptVariant(
            id="chinese_tea",
            intent="The tea is poured, the covenant is sealed",
            framing="medium",
            action="Kneeling together at a tea ceremony table, pouring tea in unison, elders implied but not shown",
            emotion_focus="Reverence — love expressed through ritual precision",
            avoid_local=["incorrect tea ceremony posture", "visible modern tableware", "cluttered table"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 6. western-romantic — 西式浪漫
# ---------------------------------------------------------------------------

_BRIEF_WESTERN_ROMANTIC = CreativeBrief(
    package_id="western-romantic",
    story="Sunlight pours through stained glass, and even heaven holds its breath.",
    visual_essence=(
        "A sun-drenched cathedral garden or chapel exterior — climbing roses on stone, "
        "golden light streaming through arched windows, petals suspended mid-air. "
        "Classic bridal elegance meeting soft romantic warmth. Nothing ironic, "
        "nothing deconstructed — pure, earnest, luminous."
    ),
    emotion="Overflowing tenderness — the kind of love that makes strangers cry",
    aesthetic="Warm golden light, creamy whites and blush pinks, soft bokeh, Renaissance painting luminosity",
    wardrobe_bride="Classic white ball gown or cathedral-train A-line, lace bodice, long tulle veil, pearl earrings",
    wardrobe_groom="Navy or charcoal three-piece suit, white pocket square, polished shoes, subtle boutonnière",
    makeup_default="Soft romantic glow, rosy cheeks, pink-nude lip, defined lashes, luminous highlight on cheekbones",
    avoid_global=[
        "gloomy overcast light",
        "modern minimalist venue",
        "trendy or ironic elements",
        "harsh direct flash",
        "extra fingers or limbs",
        "cheap tulle fabric look",
        "overly posed catalog feel",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="tender",
    variants=[
        PromptVariant(
            id="western_chapel",
            intent="Light falls on them like a blessing",
            framing="wide",
            action="Standing at the chapel entrance, golden light pouring through the doorway behind them, veil catching the glow",
            emotion_focus="Sacred joy — the threshold between before and forever",
            avoid_local=["dark interior contrast", "lost veil detail", "visible modern signage"],
        ),
        PromptVariant(
            id="western_roses",
            intent="Buried in roses, found in each other",
            framing="medium",
            action="Embracing in a rose garden archway, petals falling around them, her bouquet loose at her side",
            emotion_focus="Romantic abandon — they forgot about the photographer three seconds ago",
            avoid_local=["artificial rose look", "stiff embrace", "thorns visible"],
        ),
        PromptVariant(
            id="western_firstlook",
            intent="The first look — a thousand rehearsed words, and none come out",
            framing="close",
            action="His hand covering his mouth in emotion as he sees her, her eyes glistening, mid-laugh and mid-cry",
            emotion_focus="Raw overwhelm — the beautiful wreckage of composure",
            avoid_local=["fake tears", "dead eyes", "overly symmetrical composition"],
        ),
        PromptVariant(
            id="western_golden",
            intent="The golden hour belongs to them",
            framing="wide",
            action="Walking through a sun-drenched meadow beside the chapel, his jacket over her shoulders, golden backlight",
            emotion_focus="Quiet epilogue — the ceremony is over, and the rest of life begins",
            avoid_local=["harsh sun glare", "flat meadow", "disconnected walking"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 7. artistic-fantasy — 艺术幻想
# ---------------------------------------------------------------------------

_BRIEF_ARTISTIC_FANTASY = CreativeBrief(
    package_id="artistic-fantasy",
    story="They wandered into a painting and decided to stay.",
    visual_essence=(
        "An enchanted forest clearing lit by bioluminescent flora and a crescent moon. "
        "Crystal formations catch starlight, fireflies drift like living constellations, "
        "and the ground is carpeted in luminous moss. Reality bends — it's not fantasy "
        "for fantasy's sake, but a world that reflects their inner landscape."
    ),
    emotion="Enchanted wonder — childhood dreams made tender and adult",
    aesthetic="Jewel tones — deep emerald, amethyst, moonlit silver — with warm golden accents on skin, dreamy soft glow, storybook richness",
    wardrobe_bride="Ethereal layered tulle gown in dusty lavender or silver, celestial headpiece with tiny stars, trailing cape",
    wardrobe_groom="Dark velvet frock coat in deep plum or midnight blue, silver chain accent, poet collar",
    makeup_default="Luminous otherworldly glow, iridescent highlight on cheekbones, soft plum lip, starlight shimmer on lids",
    avoid_global=[
        "cheap Halloween costume feel",
        "plastic crystal props",
        "over-processed HDR look",
        "childish cartoon aesthetic",
        "extra fingers or limbs",
        "cluttered magical elements",
        "theme park backdrop feel",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="cool_diffused",
    pose_energy="dramatic",
    variants=[
        PromptVariant(
            id="fantasy_clearing",
            intent="The enchanted glade where time forgot its job",
            framing="wide",
            action="Standing in a moonlit forest clearing, bioluminescent flowers blooming at their feet, fireflies orbiting them",
            emotion_focus="Reverent wonder — they have stumbled into something ancient and alive",
            avoid_local=["flat forest backdrop", "uniform firefly distribution", "lost figure in darkness"],
        ),
        PromptVariant(
            id="fantasy_crystal",
            intent="Love refracted through a thousand facets",
            framing="medium",
            action="Surrounded by crystal formations catching moonlight, prismatic light scattered across their faces and clothes",
            emotion_focus="Kaleidoscopic intimacy — every angle reveals something new about them",
            avoid_local=["opaque dull crystals", "harsh rainbow overlay", "distorted reflections on skin"],
        ),
        PromptVariant(
            id="fantasy_canopy",
            intent="Crowned by stars that came down to watch",
            framing="close",
            action="Under a canopy of glowing vines, his hand cupping her face, tiny lights reflecting in their eyes",
            emotion_focus="Sacred privacy — even in a magical world, this moment is only theirs",
            avoid_local=["vines touching/wrapping bodies", "overlit faces", "CGI-looking glow"],
        ),
        PromptVariant(
            id="fantasy_path",
            intent="The road between worlds",
            framing="wide",
            action="Walking a luminous forest path that fades into mist, hand in hand, her cape billowing with unearthly wind",
            emotion_focus="Brave wonder — stepping into the unknown, but stepping together",
            avoid_local=["path looking like a game render", "stiff walking pose", "lost detail in mist"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# 8. travel-destination — 旅拍风光（圣托里尼）
# ---------------------------------------------------------------------------

_BRIEF_TRAVEL_DESTINATION = CreativeBrief(
    package_id="travel-destination",
    story="The Aegean holds its blue so they can paint their own sunset.",
    visual_essence=(
        "Santorini's caldera at golden hour — whitewashed walls, cobalt domes, "
        "bougainvillea spilling over volcanic stone. The sea is a sheet of hammered gold. "
        "They are not tourists; they are the reason the island exists. Wind-caught fabric, "
        "sun-warmed stone, salt on skin."
    ),
    emotion="Sun-drunk joy — the honeymoon started early",
    aesthetic="Cobalt blue and sun-bleached white with sunset gold, Mediterranean clarity, warm film tones, salt-air texture",
    wardrobe_bride="Flowing white Grecian gown with open back, gold sandals, wind-friendly fabric",
    wardrobe_groom="White linen shirt unbuttoned at collar, tailored beige trousers, leather sandals, sun-tanned",
    makeup_default="Bronzed Mediterranean glow, golden highlight, warm peach lip, waterproof and wind-proof, effortless beauty",
    avoid_global=[
        "overcast grey skies",
        "tourist crowds or shops",
        "green lush vegetation",
        "indoor shots",
        "extra fingers or limbs",
        "postcard-oversaturated blue",
        "cruise ship in background",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="soft_warm",
    pose_energy="playful",
    variants=[
        PromptVariant(
            id="travel_caldera",
            intent="The whole Aegean as their witness",
            framing="wide",
            action="Standing on a whitewashed terrace edge, caldera and sea behind, wind lifting her dress and his shirt, golden hour",
            emotion_focus="Expansive freedom — the world is wide and it is theirs",
            avoid_local=["dangerous cliff impression", "flat sea texture", "washed-out sky"],
        ),
        PromptVariant(
            id="travel_bluedome",
            intent="Iconic beauty, unironic love",
            framing="medium",
            action="Kissing in front of the famous blue-domed church, bougainvillea framing the edges, warm stone underfoot",
            emotion_focus="Earnest romance — yes it's the postcard spot, and they don't care",
            avoid_local=["dome color mismatch", "visible other tourists", "stiff staged kiss"],
        ),
        PromptVariant(
            id="travel_steps",
            intent="Every step down is a step into each other",
            framing="medium",
            action="Descending narrow whitewashed steps together, laughing, her hand trailing along the blue railing, golden light on walls",
            emotion_focus="Playful discovery — every corner of this island has a secret for them",
            avoid_local=["steep unsafe angle", "modern fixtures visible", "flat white walls"],
        ),
        PromptVariant(
            id="travel_sunset",
            intent="The sun sets for the last time as two, and rises tomorrow as one",
            framing="wide",
            action="Silhouetted against a molten Santorini sunset, seated on a stone wall, wine glasses beside them, sea below",
            emotion_focus="Golden finality — this is the closing scene of the greatest day",
            avoid_local=["overcooked HDR sunset", "lost silhouette detail", "floating wine glasses"],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Phase 4 映射表（merge 到 _BRIEFS）
# ---------------------------------------------------------------------------

_BRIEFS_PHASE4: dict[str, CreativeBrief] = {
    "french": _BRIEF_FRENCH,
    "minimal": _BRIEF_MINIMAL,
    "onsen": _BRIEF_ONSEN,
    "starcamp": _BRIEF_STARCAMP,
    "chinese-classic": _BRIEF_CHINESE_CLASSIC,
    "western-romantic": _BRIEF_WESTERN_ROMANTIC,
    "artistic-fantasy": _BRIEF_ARTISTIC_FANTASY,
    "travel-destination": _BRIEF_TRAVEL_DESTINATION,
}
