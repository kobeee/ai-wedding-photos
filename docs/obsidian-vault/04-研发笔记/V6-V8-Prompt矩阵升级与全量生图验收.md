# V6-V8 Prompt 矩阵升级与全量生图验收

> 日期: 2026-04-04
> 状态: ✅ 完结 — 六轮评审 A/A/A-/A/A/A，24 case 全量生图通过
> 前置: [[V5多维矩阵Harness工程记录]] / [[V5.2-Prompt层三轮Codex评审闭环]]

## 目标

V5 三审停在 A-/B/B+/A-/A/B，残留两个系统性问题：
1. 参考图选择不按 gender 过滤（solo 场景可能送入异性参考图）
2. brief 数据层无 solo 原生叙事（全靠 sanitize 兜底，质量差）

本轮目标：**全维度 A 以上**。

## 改动清单

### P1: reference_selector 加 gender 过滤

**文件**: `context/reference_selector.py`

```python
# select_references(upload_dir, *, gender="couple")
# solo female → 排除 groom 角色
# solo male → 排除 bride 角色
# couple_full slot 对 solo 降权 0.3x
```

**联动**: `routers/generate.py` + `tests/harness.py` 透传 gender 参数

### P2: briefs 补 solo 原生叙事

**文件**: `context/briefs.py` + `context/_briefs_phase4.py`

PromptVariant 新增 6 个字段：
- `solo_bride_intent / solo_bride_action / solo_bride_emotion`
- `solo_groom_intent / solo_groom_action / solo_groom_emotion`

共写了 **7 个 solo variant** 专用叙事：
| Variant | 性别 | 场景 |
|---------|------|------|
| iceland_candid | female | 极光下大笑的新娘 |
| cyber_playful | male | 霓虹墙边自信的新郎 |
| french_courtyard | female | 石墙旁手持薰衣草 |
| minimal_hands | male | 高对比侧光沉思 |
| star_fairylights | female | 星空帐篷旁旋转 |
| fantasy_canopy | male | 发光蘑菇森林仰望 |
| travel_steps | female | 圣托里尼阶梯回眸 |

补了 **8 个 wide couple** 缺失的肢体互动描述（原来只有场景没有人物动作）。

### P3: prompt_assembler 语义连贯性提升

**文件**: `context/prompt_assembler.py`

1. **`_resolve_variant_for_gender()`** — 优先用 solo_* 专用字段，无值才走 sanitize
2. **`_solo_story_adapt()`** — couple story → solo 的语法适配：
   - "The last two people" → "The bride, alone"
   - they → she/he, their → her/his, them → her/him
   - 动词单复数：remain→remains, are→is, don't→doesn't
   - `_fix_caps()` 修复句首代词大写
3. **性别差异化面部锚点**：
   - `_FACE_REALISM_BRIDE`: 毛孔、唇线、颧骨高光、真实睫毛
   - `_FACE_REALISM_GROOM`: 毛孔、下颌线、眉骨、胡茬纹理
4. **Energy 始终渲染**（不再跳过 "natural"）

### P4: slot_renderer 男性妆造

**文件**: `context/slot_renderer.py`

新增 `_MAKEUP_DESCRIPTIONS_MALE` 字典，male 场景不再用女性的 "nude lips, false lashes"。

## 评审演进

| 维度 | 一审 | 二审 | 三审 | 四审(V6) | 五审(V7/V8) | 终审(图片) |
|------|------|------|------|---------|---------|---------|
| 性别一致性 | D | B+ | A- | A | A | **A** |
| 语义连贯性 | D | C+ | B | A- | A | **A** |
| 身份锁定 | B+ | B+ | B+ | B+ | A- | **A-** |
| Avoid 完备性 | C | B | A- | A | A | **A** |
| R2 构图锁定 | B | A- | A | — | A | **A** |
| Variant 互动 | D | C | B | A- | A | **A** |

## 全量生图统计

- **24/24 case 成功**，0 失败
- 平均 ~75s/case，~$0.39/张
- 总成本 ~$9.36
- Manifest: `harness_outputs/v5_batch_20260404_124540_manifest.json`
- 25 张 R3 PNG（24 batch + 1 单测）

## 关键教训

1. **Codex 独立评审是核心驱动力** — 每轮都能发现自己的盲点，六轮迭代从 D 到 A
2. **solo 必须原生叙事** — sanitize 的正则替换最多到 B+，原生叙事直接拉到 A
3. **男女分治** — 妆造、面部锚点、参考图必须按性别区分，通用描述是性别不一致的根源
4. **wide couple ≠ 不需要互动** — 人小不代表不需要写肢体动作，否则 variant 评分必跌
5. **身份锁定 A- 是无参考图上限** — 有真实用户照片后可进一步提升

## 下一步

- [ ] 部署到 VPS 生产环境
- [ ] 用户亲自测试验证
- [ ] 前端对接新 API（session_token、makeup_style）
- [ ] Phase 2: 8K 超分、魔法笔刷、付费墙
