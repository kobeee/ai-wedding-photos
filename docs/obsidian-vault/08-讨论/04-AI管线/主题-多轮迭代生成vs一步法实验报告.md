---
title: 主题-多轮迭代生成vs一步法实验报告
tags:
  - AI管线
  - 实验
  - 验证
  - Nano-Banana-Pro
created: 2026-04-02
related:
  - "[[主题-婚纱摄影棚重构与订单找回决策清单]]"
  - "[[婚纱摄影棚重构总方案]]"
  - "[[主题-身材比例锚定方案评审]]"
---

# 多轮迭代生成 vs 一步法实验报告

## 实验背景

[[主题-婚纱摄影棚重构与订单找回决策清单]] 提出 5 层管线重构方案，核心假设是"拆阶段、让模型一次只聚焦一件事"。本实验验证该假设在 Nano Banana Pro (Gemini 3 Pro Image) 上的可行性。

## 实验条件

- 模型：Nano Banana Pro (`gemini-3-pro-image-preview`) via laozhang.ai 代理
- 参考图：3 张（新郎正脸、新郎全身、新娘全身），均为亚洲面孔
- 场景：iceland brief（冰岛黑沙滩 + 极光）
- 测试代码：`src/backend/tests/test_pipeline_v2.py`
- 生成结果：`src/backend/test_outputs/`

## 实验一：两步法身份融合（repair 语义）

### 策略

```
步骤1: text_to_image → 底图（不传参考图）
步骤2: repair_with_references → 把底图 + 身份参考图传入，要求融合身份
```

### 结果

| 策略 | 输出人种 | 身份保持 | 耗时 |
|------|---------|---------|------|
| A 一步法 | 亚洲 ✅ | 五官方向匹配 | 120.6s |
| B repair 融合 | 白人 ❌ | 完全没换过来 | 66.3s |
| C multi_ref 融合 | 白人 ❌ | 完全没换过来 | 58.2s |

### 分析

`repair_with_references` 和 `multi_reference_generate` 调的是**同一个 API endpoint**（`generateContent`），区别只是 prompt 措辞。策略 B 的 repair prompt 写了 "Make the smallest necessary change"，模型选择保守策略不动脸。策略 C 虽然用了生成 prompt，但底图人脸作为视觉锚点太强，身份照压不过。

### 结论

**repair 语义 + 底图人脸 = 身份融合失败。** 模型不具备跨身份替换能力（在 repair 模式下）。

## 实验二：三轮迭代法（生成语义）

### 策略

```
Round 1: text_to_image — 纯文本生成场景底图（不传参考图）
Round 2: image_to_image — 传入 R1 底图，定向精修服饰/动作/手势
Round 3: multi_reference_generate — R2 作为构图参考（第一张图）+ 身份参考图，
         使用生成语义 prompt："Generate a new image that combines the SCENE 
         from image 1 and the FACIAL IDENTITY from remaining references"
```

### 关键 prompt 差异

Round 3 的 prompt 与失败实验的核心区别：

1. **生成语义**而非修复语义——"Generate a new image" 而非 "Make the smallest change"
2. **明确区分图片角色**——"The first reference image provides the exact scene composition... The remaining reference images show the real couple"
3. **枚举具体面部特征**——"identical eye shape, nose bridge contour, jawline angle, lip proportions, skin tone"

### 结果

| 阶段 | 输出 | 耗时 |
|------|------|------|
| R1 场景底图 | 白人情侣，场景极高质量（蕾丝纹理、岩石质感、极光层次） | 60.5s |
| R2 服饰精修 | 保持场景，裙摆飘逸感增强 | 25.7s |
| R3 身份注入 | **亚洲情侣** ✅，场景构图保持（岩石、海浪、极光位置一致） | 50.1s |
| 一步法对照 | 亚洲情侣 ✅，全新构图 | 33.1s |

### 分析

1. **身份注入成功**——R3 确实把白人面孔替换为亚洲面孔，同时保持了 R1/R2 的场景构图
2. **场景质量提升**——R1 不扛身份压力时，场景细节（蕾丝纹理、岩石质感）明显更精致
3. **身份保持仍有差距**——新郎胡子丢失，五官"偏清秀"，和参考图不完全一致
4. **成本 3 倍**——$0.39 vs $0.13，延迟 136s vs 33s

## 核心发现

### 1. Prompt 语义决定身份注入成败

- ❌ "Make the smallest necessary change" → 模型不敢动脸
- ❌ 底图和身份图并列无区分 → 模型跟着底图脸走
- ✅ "Generate a new image that combines SCENE from image 1 and IDENTITY from images 2-4" → 身份注入成功

### 2. 分步生成的场景质量确实更高

学术支撑：
- [DeCoT (2025)](https://arxiv.org/html/2508.12396)：分解复杂指令为子任务，语义准确率显著提高
- [PRISM (2026)](https://openreview.net/forum?id=jxyEci13Dd)：子组件独立处理再合并，复杂场景提升 7.4%
- [Google 官方](https://developers.googleblog.com/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/)：推荐"split your request into steps"

### 3. 身份保持的瓶颈在参考图

根据 [Nano Banana Pro 最佳实践](https://blog.laozhang.ai/en/posts/nano-banana-pro-face-consistency-guide)：
- 当前：3 张参考图，无角度要求，无人脸占比筛选
- 最佳：6 张，正面+3/4左+3/4右，人脸占 30-50% 画幅，最低 1024×1024
- 超过 10 张反而会退化（averaging variation）

### 4. 不需要引入第二个模型

Nano Banana Pro 自身的 `multi_reference_generate` 在正确 prompt 下就能完成身份注入。InfiniteYou/ReActor 等专用模型是备选方案，但当前阶段不必引入。

## 已知问题

1. **多人身份互相干扰**——[Google 论坛](https://discuss.ai.google.dev/t/identity-preservation-breakdown-in-multi-person-image-generation-and-upscaling/120276) 确认是已知问题，无官方解决方案
2. **VLM 质检代理不稳定**——laozhang.ai 的 gemini-3.1-pro 通道有连接中断问题，质检分数不可靠
3. **身份保持稳定性不够**——同样参考图，多次生成的人脸会有差异

## 下一步

1. **升级参考图筛选**（`reference_selector.py`）
   - 用 VLM 评估人脸角度、占比、光线质量
   - 要求最低 6 张，正面+侧面+全身
   - 前端上传引导用户拍指定角度

2. **实现三轮管线原型**
   - Round 1: text_to_image 场景生成
   - Round 2: image_to_image 细节精修
   - Round 3: multi_reference_generate 身份注入（生成语义 prompt）
   - 集成到 `routers/generate.py` 的 `_run_generation`

3. **改进 identity lock prompt**
   - 枚举具体面部特征（eye shape, nose bridge, jawline, lip, skin tone）
   - 放在 prompt 最前面
   - 正面强化（"maintain"）而非否定（"don't change"）

4. **扩大实验样本**
   - 用更多参考图（6张+多角度）重新测试
   - 测试多个套餐场景（不只 iceland）
   - 收集身份保持的量化数据

## 相关文件

- 测试脚本：`src/backend/tests/test_pipeline_v2.py`
- 生成结果：`src/backend/test_outputs/`
  - `A_one_shot.png` — 实验一一步法
  - `B_base_no_identity.png` — 实验一底图
  - `B_fused.png` — 实验一 repair 融合（失败）
  - `C_scene_guided_with_identity.png` — 实验一 multi_ref 融合（失败）
  - `D_r1_scene.png` — 实验二 Round 1 场景底图
  - `D_r2_refined.png` — 实验二 Round 2 服饰精修
  - `D_r3_identity.png` — 实验二 Round 3 身份注入（成功）
  - `D_oneshot_improved.png` — 实验二一步法对照
