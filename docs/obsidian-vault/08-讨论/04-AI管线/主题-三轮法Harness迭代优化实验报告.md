# 三轮法 Harness 迭代优化实验报告

> 日期：2026-04-02 ~ 2026-04-03
> 参与：Claude Opus 4.6 (主控) + Codex GPT-5.4 (评审)
> 工具：`src/backend/tests/harness.py`

## 一、实验目标

在三轮迭代生成法（R1 场景 → R2 精修 → R3 身份注入）的框架下，通过系统化的 prompt 调优找到**最具泛化且效果最好的组合**。

评判标准：
1. 服饰、场景、动作符合套餐 brief
2. 身材比例自然，无解剖异常
3. 人脸必须像参考图中的真人（核心难点）
4. 摄影质量：大片感、色调、真实感

## 二、实验条件

- **模型**：gemini-3-pro-image-preview (Nano Banana Pro) via laozhang.ai
- **参考图**：5 张（couple_full + bride_portrait + bride_full + groom_portrait + groom_full），经 reference_selector 筛选后实际使用 3 张
- **套餐**：iceland（冰岛黑沙滩+极光）
- **Variant**：iceland_intimate（close-up，额头相触）
- **评审**：每轮生成后交给 Codex GPT-5.4 从 6 个维度打分

## 三、四轮迭代过程

### Round 1: Baseline（三轮法标准 prompt）

**策略**：不做任何调整，直接用现有 prompt 组装器输出

**Codex 评审**：**B**

| 维度 | 分 |
|------|-----|
| 身份匹配 | 7/10 |
| 场景/服饰/姿势 | 9/10 |
| 身材比例 | 8/10 |
| 妆造/造型 | 8/10 |
| 摄影质量 | 7/10 |
| 管线评估 | 8/10 |

**问题**：
- 新娘脸被美化（下颌线变瘦、鼻梁理想化）
- 裁切偏远，不够 close-up
- 皮肤过于光滑，有 AI 感

**Codex 建议**：强化身份锁定、要求 85mm 镜头感、增加真实皮肤纹理。

---

### Round 2: V2（基于 Codex 反馈优化）

**策略变化**：
- R2 增加"Crop tighter: 85mm portrait lens close-up"
- R3 增加新娘面部特征描述（圆脸、不许瘦脸）
- Avoid 增加 airbrushed skin、face slimming

**Codex 评审**：**B+**

| 维度 | 分 | vs Baseline |
|------|-----|-------------|
| 身份匹配 | 8/10 | +1 |
| 场景/服饰/姿势 | 8/10 | -1 |
| 身材比例 | 9/10 | +1 |
| 妆造/造型 | 8/10 | 0 |
| 摄影质量 | 8/10 | +1 |
| 管线评估 | 9/10 | +1 |

**问题**：新娘白纱被深色披肩大面积遮挡（模型自由发挥加了黑色围巾），brief 不够严格。

---

### Round 3: V3（修复白纱可见度）

**策略变化**：
- Brief 覆盖 wardrobe_bride，明确"NO dark shawl, wrap, jacket"
- R3 增加"白色蕾丝婚纱必须清晰可见"
- 新娘头发锁定"中等长度直黑发"

**Codex 评审**：**D**

**严重问题**：
- R2 的 "crop tighter" 指令过于激进，把脸都裁掉了
- R3 拿到残缺的构图参考，输出了双联画（diptych）
- 白纱和身份都修好了，但格式是硬伤

**教训**：**裁切控制只能放在 R1，R2 绝不能改构图**。

---

### Round 4: V4（综合最优方案）

**策略变化**：
- R1 控制裁切（通过 brief variant 的 framing 字段）
- R2 铁律：6 条精修指令，每条都强调"不改构图"
- R3 开头加"OUTPUT FORMAT: Generate exactly ONE single photograph"
- Avoid 增加 diptych/collage/split-screen/multi-panel

**Codex 评审**：**A-**

| 维度 | 分 | vs Baseline |
|------|-----|-------------|
| 身份匹配 | 8.5/10 | +1.5 |
| 场景/服饰/姿势 | 9/10 | 0 |
| 身材比例 | 9/10 | +1 |
| 妆造/造型 | 8.5/10 | +0.5 |
| 摄影质量 | 8.5/10 | +1.5 |
| 管线评估 | 9/10 | +1 |

**Codex 结论**：适合人工审核+交付的生产模式。新娘脸部精确度差最后一口气，暂不适合全自动。

## 四、核心发现

### 1. R2 铁律：绝不改构图

V3 的双联画灾难证明：R2 的"crop tighter"指令会让模型重新诠释整张照片。R2 的唯一职责是**在既有画面内做细节增强**。

### 2. 身份锁定要按性别分别描述

泛泛的 "preserve identity" 不如具体描述有效。按性别枚举面部特征（脸型、发型、胡须、五官轮廓）能显著提升身份保持。

### 3. Avoid 清单是防御性武器

每次遇到的意外问题（黑披肩、双联画、瘦脸美化），加入 avoid 后下一轮都能修正。Avoid 清单应随实验积累持续扩充。

### 4. Brief 的 wardrobe 描述要足够具体

"Flowing white gown" 太宽泛，模型会自由发挥加披肩。必须明确 "NO dark shawl, wrap, jacket, or covering obscuring the gown"。

### 5. 生成语义 vs 修复语义是成败关键

R3 的 prompt 必须是 "Generate a new image that combines SCENE from image 1 and IDENTITY from images 2-4"，绝不能用 "Make the smallest change"。

## 五、V4 Prompt 模板（可直接落地）

### R3 身份注入 prompt 核心结构

```
You are a world-class wedding photographer creating the final editorial image.

Generate a new image that combines the SCENE COMPOSITION from the first 
reference image and the FACIAL IDENTITY from the remaining reference images.

[场景说明：第一张图提供构图/光线/服饰/姿势/背景]
[身份说明：后续图提供真人面部特征，枚举具体五官]
[Brief 上下文：故事/风格/服饰/情绪]
[Variant 上下文：这张照片的意图/构图/动作]
[关键规则：场景来自图1，脸来自后续图，不要平均混合]
[Avoid 清单]
```

## 六、成本汇总

| 实验 | API 成本 | 耗时 |
|------|---------|------|
| Baseline | ~$0.39 | 77s |
| V2 | ~$0.39 | 118s |
| V3 | ~$0.39 | 100s |
| V4 | ~$0.39 | 161s |
| Codex 评审 ×4 | ~$0.30 | ~15min |
| **总计** | **~$1.86** | **~25min** |

## 七、下一步

1. **固化 V4 prompt 到生产代码**：更新 `context/prompt_assembler.py`，新增三轮管线模式
2. **泛化验证**：用 cyberpunk/french/chinese-classic 等不同套餐跑 harness
3. **参考图升级**：从 3 张提升到 6 张（正面+侧面），验证身份保持提升幅度
4. **全自动化门槛**：VLM 质检 + 身份专项评分 → 自动决策是否需要返工

## 八、相关文件

- Harness 脚本：`src/backend/tests/harness.py`
- 生成结果：`src/backend/harness_outputs/`
- 旧实验报告：`主题-多轮迭代生成vs一步法实验报告.md`
- 重构总方案：`docs/obsidian-vault/02-架构/婚纱摄影棚重构总方案.md`
