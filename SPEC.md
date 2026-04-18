# SPEC.md — "新手看完必须想用"

Target persona: **一个对 Gemini CLI 有一点点兴趣、但没用过 `gemini-evolve`、也没深入用过 gemini-cli 的新手**。Ta 打开 README 后滚动 30 秒决定去留。

Scope: **只改文档**。不改 code。README.md / README.zh.md / docs/*.md / 新增 docs 里的示例或截图说明可以；改 code 一律 FAIL。若 generator 认为需要新 feature，必须在 PR note 或生成回复里**明确列出建议**，但不得自行实现。

Target files:
- `/Users/lich/ws/gemini-evolve/README.md`
- `/Users/lich/ws/gemini-evolve/README.zh.md`
- `/Users/lich/ws/gemini-evolve/docs/RUNBOOK.md`
- 可新增：`docs/QUICKSTART.md` / `docs/FAQ.md` / `docs/EXAMPLES.md`（若能显著降低门槛）

## 完成条件（每条必须可判决 PASS / FAIL）

### C1 — 30 秒 hook
**条件**：README 开头（前 20 行，title 之后）必须包含：
- 一句话"解决什么问题"（不是"what it is"，而是"what pain it removes"）
- 一段具体的 "before → after" 例子（比如 `GEMINI.md` 被 evolve 前长啥样、evolve 后变成啥样，或者改进了什么具体行为）
- 不超过 3 行的"为什么是我需要的"

**验证**：critic 读前 20 行，能 1 句话复述出"这是给谁的 / 解决啥"，且能指出"before/after"在哪里。

### C2 — 5 分钟上手
**条件**：从全新用户安装到看到"第一次成功运行"的时间 ≤ 5 分钟，步骤 ≤ 5 步。每一步都要：
- 能直接复制粘贴运行
- 列明前置依赖（Python 版本、`gemini` CLI 是否装了、API key / auth 方式）
- 有"成功长啥样"的预期输出片段

**验证**：critic 从 bash 空白环境模拟 `python3 --version` → 到 `gemini-evolve evolve --dry-run` 成功跑通需要的步骤数 ≤ 5。若任一步"预期输出"缺失 → FAIL。

### C3 — Wow moment 可视化
**条件**：README 必须有 **至少一个**以下能让新手"哦！我想试"的元素：
- asciinema / GIF / 静态截图展示真实运行输出（进化前 vs 进化后对比）
- 一段完整的 before/after 文本 diff，带高亮说明改进了什么
- 一个"真实战果"指标（如：`judge 打分 6.2 → 7.8，耗时 3 分钟`）

注：GIF 可以暂时用占位符 + 说明"docs/assets/demo.gif coming soon"，但至少要有一段**文字形式的 before/after 对比块**落地在 README 里。

**验证**：critic grep README 能找到 before/after 块或指标数字。找不到 → FAIL。

### C4 — 差异化 / "这不就是 X" 答辩
**条件**：README 要有一段（标题建议 "Why not just X?" 或 "对比"）明确回答至少 2 个质疑：
- 为什么不直接人工改 `GEMINI.md`？
- 为什么不直接让 Gemini "帮我优化一下这个 prompt"？
- 和 DSPy / GEPA / PromptLayer / promptfoo 之类的区别是什么？

每个回答要 ≤ 3 句，有具体论据（比如 "holdout 对比防过拟合" / "size/growth 硬门禁防 prompt 膨胀"）。

**验证**：critic 搜 "Why not" / "对比" / "vs" 章节，检查是否回答了 ≥ 2 个具体质疑。

### C5 — 前置依赖与坑点
**条件**：新增或补全一节"Prerequisites"（中英双语），明确：
- 需要 `gemini` CLI 已安装（链接官方安装指南）
- Gemini CLI 鉴权方式（OAuth / API key）以及如何验证可用
- Python 版本要求（具体到 3.10+ / 3.11+，从 pyproject.toml 反查）
- macOS / Linux 支持情况（launchd 只在 mac 可用这种坑）

另外需要一个 **Troubleshooting** 或 **FAQ** 小节，至少覆盖 3 个高概率卡点（常见错误信息 → 原因 → 解决方案）。

**验证**：critic 检查 "Prerequisites" 或 "前置" 节存在，且包含 Python 版本 + gemini CLI 安装指引 + auth 指引 + 平台限制。FAQ/Troubleshooting 节 ≥ 3 条。

### C6 — 最小可运行示例（粘贴即跑）
**条件**：README 或 `docs/QUICKSTART.md` 必须有一段 "copy-paste everything" 的完整 shell 会话块，从 clone 到第一个 output 文件产生，一次贴完就能跑。不能让用户跳来跳去拼命令。

**验证**：critic 找到这个 block，从头跑（或至少在模拟环境 dry-run）确认每一步都能执行且顺序正确。

### C7 — 中英文一致 + 新手语气
**条件**：
- `README.md` 和 `README.zh.md` 结构对齐：C1–C6 的内容两边都有。
- 中文 README 不能是机翻味，用户视角、有感情、有"要不要试一下"的召唤。
- 英文 README 避免 insider jargon 堆砌（如果第一次出现 GEPA / DSPy / holdout / tournament selection，要有 1 句括号解释）。

**验证**：critic 逐节对比中英结构；检查 README 里前 3 个技术术语是否有解释。

## APPROVE 判定

Critic 扮演 "完全不懂但对 Gemini CLI 感兴趣的新手"，并且必须**真看 README 全文**（不是 skim）。

4 维评分：
- **Hook 力** (0-10) — C1 + C3
- **上手门槛** (0-10) — C2 + C5 + C6
- **说服力 / 差异化** (0-10) — C4
- **双语完整度** (0-10) — C7

**PASS 门槛**：4 维全 ≥ 8；critic 必须能回答"我看完会不会真的去 `pip install` 跑一下"且答案是 YES 并附理由。

**FAIL 触发**：
- 任一 C1–C7 硬性条件未满足
- 任一维度 ≤ 7
- Critic 感到"还是不想用"/"看不懂这是干啥的"/"怕装完用不起来"

## Out of scope（critic 不要扣分）

- 代码改动（本轮不做）
- Logo / 品牌视觉（本轮不做）
- 网站 / landing page（本轮不做）
- 正式 GIF 制作（占位符允许）
