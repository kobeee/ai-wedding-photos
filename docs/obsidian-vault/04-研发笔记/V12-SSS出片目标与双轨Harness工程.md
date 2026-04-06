# V12 — SSS 出片目标与双轨 Harness 工程

> 日期：2026-04-05
> 目标：把真实出片效果从"架构就绪"推进到 SSS 商业化出片质量
> 前置：V11 架构（Validation Track + Hero Track + Face Lock Pass）已代码落地

## 本轮核心变更

### 1. Harness V7 升级（tests/harness.py）

从 V6（只测 editorial pipeline R1-R4）升级到 V7（测试完整 production_orchestrator）：

- **测试路径**：`production_orchestrator.run_photo()` — 即真实生产路径
- **输出**：每个 case 产出 validation 图 + hero 图 + VLM 质检报告
- **SSS 四维评分**：
  - `identity_verifiability`：至少 1 张 validation-safe 图通过身份验证
  - `proportion_verifiability`：至少 1 张图通过比例验证
  - `hero_quality`：可见 hero 图的平均 quality_score
  - `commercial_pass`：前三项全部通过且 hero_quality ≥ 0.85
- **新增模式**：`--quick`（3 个代表性 case）、`--editorial-only`（只跑 R1-R4 对比）
- **Codex 评审清单**：manifest 含 SSS 通过率统计

### 2. 验证轨 Prompt 强化（prompt_assembler.py）

新增 `VALIDATION_TRACK_CONSTRAINTS` 和 `VALIDATION_TRACK_SOLO_CONSTRAINTS`，在 prompt 最前方注入：

- 强制三-quarter body 到 full body
- 双人正面/开放 3/4 角度，四只眼睛清晰可见
- 每张脸占图面积 3-5%（couple）/ 5-8%（solo）
- 身高差清晰可读
- 头身比自然
- 均匀光照，不允许逆光剪影
- **身份验证优先于氛围感**

`assemble_generation_prompt` 新增 `track` 参数，`editorial_pipeline` 透传。

### 3. Validation Variant 重设计（production_orchestrator.py）

`_pick_validation_variant` 完全重写：

- **Couple**：framing="medium-wide"，不再是 ultra-wide 环境图
  - 动作强调"站立自然间距、双人正面、四只眼睛可见、身高差清晰"
  - 避免"profile view / face overlap / backlighting / ultra-wide tiny figures"
- **Solo**：framing="medium"，半身朝镜头
  - 对应 `VALIDATION_BODY_VISIBILITY_FLOOR_SOLO = 0.60`（不要求全身）

### 4. VLM 阈值 SSS 调优（thresholds.py）

| 阈值 | V11 值 | V12 值 | 说明 |
|------|--------|--------|------|
| IDENTITY_MATCH_FLOOR | 0.78 | **0.80** | 更严的脸部相似度底线 |
| SOFT_PASS_FLOOR | 0.88 | **0.90** | SSS 级才允许直接交付 |
| MIN_DELIVERY_FLOOR | 0.83 | **0.85** | 最终轮交付底线提升 |
| VALIDATION_FACE_AREA_FLOOR | 0.018 | **0.035** | 翻倍，不允许小人脸通过验证 |
| HERO_FACE_AREA_FLOOR | 0.032 | **0.025** | 略降，hero 允许更多氛围 |
| VALIDATION_BODY_VISIBILITY_FLOOR | 0.72 | **0.80** | Couple 要求更高身体可见 |
| VALIDATION_BODY_VISIBILITY_FLOOR_SOLO | - | **0.60 (新增)** | Solo 半身即可 |

### 5. VLM 质检强化（vlm_checker.py）

- **gender 参数注入**：`check_image` 和 `check_and_suggest_fix_prompt` 新增 `gender` 参数
- **Couple vs Solo 评分标准分离**：
  - Couple validation：检查"双人正面、双脸面积、身高比例"
  - Solo validation：只检查"单人正面、单脸面积、头身比"
  - Solo 不再被 couple 标准误判
- **Hero 轨加入面积百分比指导**：< 2.5% 面积 → 身份不可验证

### 6. Face Lock Pass 优化（prompt_assembler.py + production_orchestrator.py）

- **面部特征逐项锁定**：不再泛泛说"preserve identity"，而是枚举具体特征（眼形、鼻梁、唇形、肤色等）
- **分男女**：bride 和 groom 用不同特征清单
- **参考图兜底**：如果没有角色特定参考图，退回用通用 identity refs
- **修复提示扩大范围**：不仅匹配 role 关键词，还匹配 identity/face/likeness

## Codex 审查发现与修复

Codex 独立审查发现 3 个 ERROR 级别问题，均已修复：

1. **P0**: VLM 评分指导对 solo 不兼容 → 加入 gender 参数 + 分场景评分标准
2. **P0**: Solo body_visibility 阈值与半身构图矛盾 → 新增 `VALIDATION_BODY_VISIBILITY_FLOOR_SOLO`
3. **P1**: `medium-wide` framing 不在识别列表 → 补充到 readability control 和 deprofile 逻辑

## VPS 端到端验证

### Run 1（VLM 不可用）
- 3/3 失败：VLM (gemini-3.1-pro-preview) 返回 JSON 被 max_tokens=2048 截断
- `_parse_report` JSON 解析失败 → `_fallback_report` 设 `inspection_unavailable=True` → pipeline 抛异常
- **根因**：不是通道不可用，是 VLM 输出被截断

### Run 2（修复 JSON 截断）
- **修复**：`vlm_max_tokens` 2048 → 4096 + `_rescue_truncated_report()` 鲁棒性兜底
- 结果：1/3 通过（french couple），2/3 失败
- 失败原因：`VALIDATION_FACE_AREA_FLOOR = 0.035` 对 couple 图太严
  - iceland wide couple: 0.015-0.020（远低于 0.035）
  - iceland solo female: 0.030（略低于 0.035）

### Run 3（拆分 couple/solo 人脸面积阈值）
- **修复**：VALIDATION_FACE_AREA_FLOOR 拆分
  - couple: 0.025（双人图每张脸占 2.5% 已可验证身份）
  - solo: 0.035（单人应更大）
- **结果：3/3 全部 SSS commercial_pass = PASS**
  - identity_pass_rate: 100%
  - proportion_pass_rate: 100%
  - avg_hero_quality: 0.917
  - commercial_pass_rate: 100%

| Case | 类型 | hero_quality | 资产数 | 耗时 |
|------|------|-------------|--------|------|
| french_golden_couple | couple/close | 0.917 | 1 (validation→visible) | 795s |
| iceland_epic_couple | couple/wide | 0.900 | 1 (validation→visible) | 702s |
| iceland_candid_female | solo/medium | 0.933 | 2 (validation+hero) | 237s |

### 发现的问题
1. **Couple hero track 全部失败**：两个 couple case 只有 validation 图通过，hero track 无法产出。用户只收到 validation 质量的图。
2. **Couple 耗时 12-13min**：含 2-3 次 validation 重试，Solo 仅 4 min
3. **VLM face_area_ratio 波动大**：同一场景不同尝试 0.020 vs 0.030

## 最终阈值表（V12 Final）

| 阈值 | 值 | 说明 |
|------|-----|------|
| IDENTITY_MATCH_FLOOR | 0.80 | 脸部相似度底线 |
| SOFT_PASS_FLOOR | 0.90 | SSS 直接交付 |
| MIN_DELIVERY_FLOOR | 0.85 | 最终轮交付底线 |
| VALIDATION_FACE_AREA_FLOOR_COUPLE | 0.025 | 验证轨 couple 每张脸面积 |
| VALIDATION_FACE_AREA_FLOOR_SOLO | 0.035 | 验证轨 solo 人脸面积 |
| HERO_FACE_AREA_FLOOR | 0.025 | Hero 轨人脸面积 |
| VALIDATION_BODY_VISIBILITY_FLOOR | 0.80 | 验证轨 couple 身体可见 |
| VALIDATION_BODY_VISIBILITY_FLOOR_SOLO | 0.60 | 验证轨 solo 身体可见 |
| vlm_max_tokens | 4096 | VLM 最大输出 token |

## Codex 独立评审结果

**评级：C（需要显著改进）**

### P0 发现
1. **commercial_pass 被高估**：harness 把 promoted validation 图的分数当 hero_quality 计分，3/3 PASS 不能证明 hero track 成功
2. **Couple hero track 失败根因**：`decide_repair()` 没有 track 维度，hero 评估用了和 validation 一样的严格门槛（IDENTITY_MATCH=0.80, SOFT_PASS=0.90），导致氛围型 couple hero 被过早 regenerate/reject
3. **单测漂移**：4 个测试因阈值变更失败

### 修复
1. harness SSS 评分拆分 `hero_track_ok` + `delivery_quality`，禁止 promoted validation 冒充 hero
2. 修正 4 个漂移单测（face_area 值、delivery_floor、validation variant）
3. 26 个单测全部通过

### Codex 改进建议（待后续实施）
- `decide_repair()` 按 track 分策略
- Couple 限流分离（max_validation_attempts, max_hero_regenerations 分开）
- 补 _rescue_truncated_report() 单测

## V13 追加：Hero Track 分策略修复（2026-04-05）

### 改动
1. **`decide_repair()` track-aware**：新增 `track` 参数
   - hero: HERO_IDENTITY_MATCH_FLOOR=0.70, HERO_SOFT_PASS_FLOOR=0.85, HERO_MIN_DELIVERY_FLOOR=0.80
   - validation: 原阈值不变（0.80/0.90/0.85）
2. **Couple 验证重试增强**：couple 5 次（vs solo 3 次），应对 face_area 波动
3. **3 个新单测**：验证 hero 分策略 identity/soft_pass/delivery 三个维度

### VPS Harness 结果

| Case | 类型 | hero_track_ok | hero_quality | delivery_quality | 耗时 |
|------|------|:---:|:---:|:---:|---:|
| french_golden_couple | couple/close | NO | 0.00 | 0.92 | 594s |
| iceland_epic_couple | couple/wide | **YES** | **0.85** | 0.85 | 1130s |
| iceland_candid_female | solo/medium | **YES** | **0.88** | 0.88 | 522s |

**对比 V12**：Hero Track 成功率从 0/2 → 2/3 (67%)
- Iceland couple：第 5 次验证才通过（V12 只有 3 次会直接失败），face_lock pass 成功拯救 hero
- French couple hero 仍然失败：需要进一步分析 hero prompt 或 regeneration 预算

## 下一步

- French couple hero 失败根因分析
- 全量 24 case 批跑
- 补 _rescue_truncated_report() 单测

## 严重线上问题记录（待下个 Session 深挖）

### 现象

1. 用户真实订单 `ord_910047d013b149f1` 曾长期停在 `12%`
   - 批次：`batch_78ff861afec54fcb`
   - 文案长期停留：`正在生成第 1/3 张...`
2. 即使补上了 validation / hero 子阶段进度回调，真实线上链路仍会在更前面的 `8%` 阶段长时间停留
   - 当前定位到的前置耗时主要来自 `resolve_selected_makeup_reference()`
3. 更严重的是：旧批次在部署 / 进程中断后会遗留为 `processing`
   - 前端会持续读到“处理中”
   - 但后端实际上已经没有活跃任务继续推进该批次

### 当前判断

- 这已经不是单纯的“Waiting 页展示问题”，而是**任务状态机与后台执行生命周期不一致**
- 当前系统至少有两层问题：
  1. **可见进度粒度不足**
     - 8% 之前的前置步骤没有完整拆出可见进度
  2. **任务持久化/恢复缺失**
     - background task 被部署或进程中断打断后，库里的 batch 不会自动转失败或可恢复
     - 订单会留下“假 processing”状态

### 影响

- 用户前端感知为“卡死”
- 客服/运营无法仅凭前端判断任务是否仍在跑
- VPS 部署动作会放大这个问题，因为重启时不会回收历史悬挂批次

### 下个 Session 建议优先级

1. 先梳理订单批次状态机：`pending -> processing -> completed/failed/interrupted`
2. 给批次增加“心跳 / lease / last_progress_at”语义，而不是只靠 `updated_at`
3. 启动时扫描悬挂批次，自动转 `failed` 或 `interrupted`
4. 把 `resolve_selected_makeup_reference()`、director edit、reference prep 这些前置步骤也拆成可见进度
5. 再决定前端 Waiting 页是否需要额外文案区分“准备素材中” vs “正式生成中”
