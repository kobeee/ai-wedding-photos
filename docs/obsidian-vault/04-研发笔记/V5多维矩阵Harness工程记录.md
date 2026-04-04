# V5 多维矩阵 Harness 工程记录

> 日期: 2026-04-03~04
> 状态: ✅ 完结 — 三审 A-/B/B+/A-/A/B → 终审 A/A/A-/A/A/A（24 case 全量生图通过）
> 详见: [[V5.2-Prompt层三轮Codex评审闭环]] → [[V6-V8-Prompt矩阵升级与全量生图验收]]

## 目标

V4 只验证了 iceland × intimate × couple 单一场景达到 A-。
V5 目标：建立系统化多维测试矩阵，暴露跨场景弱点，把所有条件交叉下的输出稳定在高水位线。

## 本轮完成

### 1. V4 教训回灌生产代码 (prompt_assembler.py)

| 改进 | 位置 | 原理 |
|------|------|------|
| 全局 anti-diptych 硬约束 | `_GLOBAL_HARD_AVOIDS` | 所有 prompt 自动追加 6 项硬约束 |
| R2 构图铁律 | `R2_COMPOSITION_LOCK` | V3 血泪教训：R2 改构图必崩 |
| R3 生成语义身份融合 | `assemble_identity_fusion_prompt()` | V4 验证最优：Generate combining... |
| 性别枚举式身份锁定 | `_identity_lock_by_gender()` | "preserve identity" 无效，必须枚举面部特征 |

### 2. V5 矩阵 Harness (tests/harness.py)

**24 个 case 覆盖矩阵：**
- 10 套餐全覆盖（每个 2-3 case）
- close × 8 / medium × 8 / wide × 8
- couple × 16 / female × 4 / male × 4
- 4 种光照自然跟随套餐

**CLI 用法：**
```bash
python tests/harness.py --list                    # 列出 24 case
python tests/harness.py --dry-run                 # 只生成 prompt
python tests/harness.py --package cyberpunk       # 按套餐过滤
python tests/harness.py --framing close           # 按构图过滤
python tests/harness.py --gender female           # 按性别过滤
python tests/harness.py --case xxx                # 跑单个 case
LAOZHANG_API_KEY=xxx python tests/harness.py      # 全量跑
```

**输出：**
- 每 case: `_R1.png` + `_R2.png` + `_R3.png` + `_meta.json` + `_prompts.json`
- 批跑: `_manifest.json`（含维度统计）

### 3. Codex 评审协议

`docs/obsidian-vault/08-讨论/04-AI管线/主题-V5多维矩阵评审协议.md`

- 单 case 评审模板：三维评分 + 硬失败 + 分轮评价
- 跨维度对比分析：套餐/构图/性别/光照/交叉弱点矩阵
- 最终输出��Top 3 弱点 + Top 3 强点 + 修复建议 + 下轮实验设计

## 下一步

1. 注入 `LAOZHANG_API_KEY`
2. 先跑 1 个探路 case 确认 API 通
3. 全量跑 24 case（~$9.36，~50min）
4. 生成结果 + manifest 丢给 Codex 评审
5. 根据弱点维度定向修复 prompt/brief
6. 再跑弱点子集验证

## 预估成本

- 24 case × 3 轮 × $0.13/轮 ≈ **$9.36**
- Codex 评审 ≈ $2-3
- 总计 ≈ **$12-13**

## 关键文件

| 文件 | 用途 |
|------|------|
| `src/backend/context/prompt_assembler.py` | V5 prompt 组装器（含 R3 融合 + 身份锁定） |
| `src/backend/tests/harness.py` | V5 矩阵 harness |
| `docs/.../主题-V5多维矩阵评审协议.md` | Codex 评审协议 |
| `src/backend/harness_outputs/` | 生成结果输出目录 |
