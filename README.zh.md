# gemini-evolve

[English](README.md) | 简体中文

> **别再手动改你的 `GEMINI.md` 了。让 Gemini 自己调它——有 holdout 测试和硬门禁兜底，永远不会偷偷让效果变差。**

只要你用过 [Gemini CLI](https://github.com/google-gemini/gemini-cli)，你电脑里多半有一份 `GEMINI.md`。如果它写了一段时间了，里面大概率有一些模糊的规则、重复的建议，或者"回头再整理"的 TODO 没删。

`gemini-evolve` 跑一个小小的优化循环：**它会变异你的 instructions、把每个变体扔进 Gemini CLI 在真实任务上打分、然后只有 holdout（没见过的测试集）说它真变好了，才肯写回磁盘。**

### Before → After（示例，非 benchmark）

原始 `~/.gemini/GEMINI.md`：

```markdown
# My Gemini Instructions
- try to be concise
- generally avoid long explanations
- if possible, use bullet points
- prefer to keep answers short
```

跑一次 `gemini-evolve evolve --apply` 之后，`sharpen_constraints` + `condense` 这两个变异策略通常会整理成这样：

```markdown
# My Gemini Instructions

## Response Style
- Answer in <=3 sentences by default; use bullets for lists of 3+ items.
- No preamble ("Sure!", "Great question!"). Start with the answer.
- Expand only when the user asks "explain" / "why" / "walk me through".
```

Holdout 分数上去了、没超大小上限，`--apply` 就把新文件写回，并把原文件存成 `GEMINI.md.<UTC 时间戳>.bak` 作为后悔药。
如果 holdout 分数**没**比 baseline 提升至少 2%，流水线会拒绝写回——绝不偷偷塞一个可能变差的版本给你。

### 为什么你会想试一下

- 你手动改 `GEMINI.md` 已经改到烦了。
- 你怀疑它在变胖，但又不敢随便删。
- 你想要"有数据的改进"，而不是"改完感觉好像顺一点"。

---

## 前置依赖

| 需要什么 | 怎么验证 | 备注 |
| --- | --- | --- |
| Python **3.11+** | `python3 --version` | 3.12 也测过 |
| `gemini` CLI 装了且已登录 | `gemini --version`，再跑 `gemini -p "hi" -o json` | 安装：[google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli)。gemini-evolve 完全走你本地的 `gemini` 进程，你 CLI 能用就它能用。具体验证顺序见下方 **30 秒 CLI 自检**。 |
| macOS 或 Linux | — | `trigger cron-*`（走 launchd）**只支持 macOS**。`trigger watch` 和 `trigger hook-*` Linux 也能跑。Windows 没测过。 |
| 有一份 `GEMINI.md` 可以进化 | `ls ~/.gemini/GEMINI.md` | 没有？Quickstart 会帮你建一个。 |

本仓库**不直接调用 Gemini SDK/API**，所有模型调用都是通过你本地的 `gemini -p ... -o json`。你 CLI 的认证/工具/skills/MCP 都原样可用。

### 30 秒 CLI 自检

如果你之前没用过 Gemini CLI，按顺序跑：

```bash
gemini --version                           # 1. 必须打出版本号，不是 "command not found"

# 2. 登录（二选一——gemini 并没有 `auth` 子命令）：
#    a) 首次用户 / Google 账号：直接跑 `gemini`（不带任何参数），
#       它会弹浏览器走 OAuth，把凭证写到 ~/.gemini/oauth_creds.json
#    b) 非交互 / CI / AI Studio key：export GEMINI_API_KEY=<你的 key>

gemini -p "say hi in one word" -o json     # 3. 必须返回一个 JSON 对象
                                           #    注意：这是一次真实调用（约 5 秒、消耗一点点 quota）
```

最后一行能返回 JSON 就算通过——gemini-evolve 会自动复用同一套认证。

---

## 5 分钟上手

完整"复制一段贴就跑"的脚本在 [docs/QUICKSTART.md](docs/QUICKSTART.md)（以下链接指向的 QUICKSTART / FAQ / EXAMPLES 目前是英文版，遇到的高频问题在本页下方表格里已经中文化）。短版本，5 步，每步都写清"跑对了应该长啥样"。

> 提示：步骤 1 跑完后 `source .venv/bin/activate` 一次，后面就可以省掉 `./.venv/bin/` 前缀。（cwd 的假设也在步骤 1 代码块里重复说明了。）

```bash
# 1. 装包——任意目录跑都行；第 3 行的 `cd` 会把你切到 gemini-evolve/，
#    后面所有步骤都假设 cwd 在这里。需要 Python 3.11+。
git clone https://github.com/LichAmnesia/gemini-evolve.git
cd gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e .
# 成功信号：pip 最后一行 "Successfully installed gemini-evolve-0.1.0 ..."
```

```bash
# 2. 两个 CLI 都能找到
./.venv/bin/gemini-evolve --version    # 期待: "gemini-evolve, version 0.1.0"
gemini --version                        # 期待：版本号（不是 "command not found"）
```

```bash
# 3. 确保有一个目标文件可以进化
mkdir -p ~/.gemini
test -f ~/.gemini/GEMINI.md || printf '# Gemini Instructions\n- be concise\n- use bullets\n' > ~/.gemini/GEMINI.md
# 成功信号: `cat ~/.gemini/GEMINI.md` 能打出内容
```

```bash
# 4. dry-run——只验约束，不写回目标文件
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
# 成功信号：打出 "PASS non_empty"、"PASS size"、"Dry run — skipping optimization."
# 注意：--dry-run 仍然会先构建 eval 数据集。默认的 --eval-source synthetic 会
#   真调用一次 gemini（约 5-10 秒、消耗一点点 quota）。
#   想要"真·零成本"的 dry-run，就给一个小 golden JSONL：
#     echo '{"task_input":"hi","expected_behavior":"respond briefly"}' > /tmp/stub.jsonl
#     ./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run \
#         --eval-source golden --eval-dataset /tmp/stub.jsonl
```

```bash
# 5. 跑一次真实的小规模进化，几分钟起步
#    默认引擎是 GEPA；加 --engine ga 可以切到更轻量的锦标赛 GA
#    默认参数下（dataset_size=10，GEPA auto=light）的大致成本：
#      ~20 次 gemini 调用，挂钟 3-5 分钟，花销可以忽略
#      （1 次 synthetic 数据集生成 + ~10 次 GEPA metric + baseline/holdout 打分）。
#    medium 大约 2 倍，heavy 大约 5 倍。随时 Ctrl-C 中断，
#    第 6 步 --apply 之前不会写任何文件。
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --gepa-budget light
# 成功信号：GEPA 迭代日志 + 最后的 "Evolution Results" 表格 +
#           新目录 ./output/<name>/<timestamp>/ 生成
```

表格里看到一行 `Evolution improved ... by +X%`，就打开 `output/<target>/<timestamp>/evolved.md` 看一眼。觉得可以？再跑一次加 `--apply`：

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

成功写回时，原文件会被备份到同目录的 `GEMINI.md.<UTC 时间戳>.bak`。后悔了？`cp` 回来就行。

> 第一次用：看 [docs/QUICKSTART.md](docs/QUICKSTART.md)（一段贴完就跑）、[docs/FAQ.md](docs/FAQ.md)（新手最常踩的 10 个坑）、[docs/EXAMPLES.md](docs/EXAMPLES.md)（更多 before/after 示例）。**以上三份文档目前是英文版**，核心高频坑已经在本页下面的"Troubleshooting / FAQ"表格里翻译过一轮。

---

## "这不就是 X 吗？"——三个最常被问的问题

**"为啥不直接手动改 `GEMINI.md`？"**
该手动改的你就去改——比如你已经*明确知道*哪条规则是错的。`gemini-evolve` 解决的是你**不知道**的那部分：某条规则换种写法，Gemini 的行为会不会真的变？它会拿变体在 eval 集上 A/B，答案是数据，不是猜。

**"为啥不直接让 Gemini '帮我优化下这个 GEMINI.md'？"**
那样你只拿到**一个没验证过**的重写。`gemini-evolve` 会用好几种不同变异策略（`clarity`、`condense`、`sharpen_constraints` ...）生成多个候选，每个都真的跑 Gemini CLI 打分，然后用一份从没见过的 holdout 数据再跟 baseline 比一次，最后还要过"大小 / 增长 / 最小提升 %"三道硬门禁。过拟合和 prompt 膨胀都会被卡在门口。

**"它和 DSPy / GEPA / promptfoo 什么关系？"**
- [DSPy](https://github.com/stanfordnlp/dspy) / [GEPA](https://github.com/gepa-ai/gepa) 是通用的 prompt 优化框架。我们**默认就用 GEPA 做引擎**——gemini-evolve 只是个"Gemini CLI 友好的前端"，不是替代品。
- [promptfoo](https://github.com/promptfoo/promptfoo) 是 prompt 评测工具，告诉你你写的哪个 prompt 赢。`gemini-evolve` 主动**生成**候选，并且把赢家写回 `GEMINI.md`，是个闭环。
- 独特之处：整条链路跑的都是你本地的 `gemini` CLI——同一套认证、同一套工具、同一套 skills、同一套 MCP。不用再多管一个 API key。

**术语表（第一次出现的解释）：**
- **GEPA** = *Generative Evolutionary Prompt Adaptation*，一种基于反思的 prompt 优化器。这里是默认引擎，加 `--engine ga` 可以切回内置的轻量锦标赛 GA。
- **DSPy** = Stanford 的 LM 编程框架，GEPA 住在里面。用 gemini-evolve 你**不需要写 DSPy 代码**。
- **Holdout** = 循环训练全程都看不到的那部分 eval 例子，只在最后的 before/after 对比用一次。防过拟合专用。
- **Tournament selection（锦标赛选择）** = 每一代生成 N 个变体，全部打分，留最好那个做下一代的爹。
- **Hard gate（硬门禁）** = 写回前必须通过的判据（非空、大小上限、增长上限、最小提升 %）。任一不过 → 不写盘。

---

## 可以进化的目标

| 目标 | 路径模式 | 作用范围 | 大小上限 |
| --- | --- | --- | --- |
| 全局 instructions | `~/.gemini/GEMINI.md` | 所有 Gemini CLI 会话 | 15KB |
| 项目 instructions | `<project>/.gemini/GEMINI.md` | 单个项目 | 15KB |
| Commands | `~/.gemini/commands/*.toml` | 自定义斜杠命令 | 5KB |
| Skills | `~/.gemini/skills/**/*.md` | Skill 定义 | 15KB |

项目发现默认扫描 `~/ws`、`~/projects`、`~/code`，想换路径就设 `GEMINI_EVOLVE_PROJECT_PATHS=/path/a:/path/b`。

更多 before/after 示例——改写自定义 `commands/*.toml`、评测 `skills/**/*.md`、用真实会话挖 eval 数据——这三类在 [docs/EXAMPLES.md](docs/EXAMPLES.md) 各有独立示例。

---

## 主循环长什么样

```text
目标文件
  -> 构建 eval 数据集 (synthetic | 挖会话 | 黄金集 JSONL)
  -> 校验 baseline 门禁 (非空、大小)
  -> 每一代：
       用 gemini CLI 并行生成 N 个变体
       plan 模式下给每个变体打分（plan 已经禁止执行，默认不再加 sandbox）
       锦标赛选最好的；可选交叉
  -> Holdout 上再比一次 evolved vs baseline (从没见过的例子)
  -> 保存到 output/<target>/<timestamp>/{baseline.md, evolved.md, metrics.json}
  -> 可选 --apply，并保留 .bak
```

写回前必须**全部**通过的硬门禁：

1. 内容非空。
2. 大小不超过对应类型的上限（见上表）。
3. 增长幅度不超过 `max_growth_pct`（默认 20%）。
4. Holdout 提升 ≥ `min_improvement_pct`（默认 2%）。
5. Evolved 内容确实跟 baseline 不同。

代码入口：[gemini_evolve/cli.py](gemini_evolve/cli.py)、[evolve.py](gemini_evolve/evolve.py)、[gepa_evolve.py](gemini_evolve/gepa_evolve.py)、[mutator.py](gemini_evolve/mutator.py)、[fitness.py](gemini_evolve/fitness.py)。

---

## 评测数据来源

| 来源 | 参数 | 数据 | 什么时候用 |
| --- | --- | --- | --- |
| 合成 | `--eval-source synthetic`（默认） | Gemini 基于你现在的 instructions 生成的任务 | 第一次跑，还没自己的 eval 数据 |
| 会话 | `--eval-source session` | 从 `~/.gemini/tmp/*/chats/session-*.json` 挖出来的真实消息 | 你已经用 Gemini CLI 一段时间了，想用**真实工作流**驱动优化 |
| 黄金集 | `--eval-source golden --eval-dataset data.jsonl` | 你自己整理的 JSONL | 你很清楚"什么叫好" |

会话挖掘会自动跳过疑似密钥/凭证的消息。

---

## 自动化触发

```bash
# 监听会话；Gemini 会话安静下来就触发一次进化
./.venv/bin/gemini-evolve trigger watch --apply

# macOS launchd 定时（每 N 小时一次）
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
./.venv/bin/gemini-evolve trigger cron-status
./.venv/bin/gemini-evolve trigger cron-remove

# git post-commit hook——只在提交动了 GEMINI.md / .gemini/ 时触发
./.venv/bin/gemini-evolve trigger hook-install .
./.venv/bin/gemini-evolve trigger hook-remove .
```

提醒：`cron-*` 走 launchd，所以**只有 macOS 能用**。`watch` 和 `hook-*` 在 Linux 上也 OK。

---

## Troubleshooting / FAQ

完整列表在 [docs/FAQ.md](docs/FAQ.md)。高频坑：

| 报错 | 原因 | 解决 |
| --- | --- | --- |
| `gemini CLI not found on PATH` | 没装 `gemini`，或当前 shell 找不到 | 先装 Gemini CLI，确保 `which gemini` 在同一个终端里能返回路径 |
| `No instructions targets found` | 没有 `~/.gemini/GEMINI.md`，`~/ws` / `~/projects` / `~/code` 下也没有项目 `.gemini/GEMINI.md` | 建一个，或者 `export GEMINI_EVOLVE_PROJECT_PATHS=/abs/path` 再 `discover` |
| 合成/会话 dataset 空 | `gemini` 调用失败、没会话，或者全被过滤掉了 | 改用 `--eval-source golden --eval-dataset your.jsonl`，或多用几次 Gemini CLI 再跑 `session` |
| `Improvement below threshold` | evolved 在 holdout 上没过 `min_improvement_pct` | **这不是 bug**——这是门禁在拒绝一个疑似 regression。加代数/换 eval source 再试 |
| `launchctl` 报错（`cron-install`） | 不在 macOS（没有 launchd） | 用 `trigger watch`（跨平台）或自己接 cron / systemd |
| `Not a git repository` | 工作目录不对 | `cd` 到仓库根目录再 `hook-install` |

---

## 命令总览

```text
gemini-evolve discover --type instructions|commands|skills
gemini-evolve evolve TARGET [--dry-run] [--apply]
                     [-g GENERATIONS] [-p POPULATION]
                     [--eval-source synthetic|session|golden] [--eval-dataset FILE]
                     [--dataset-size N] [--llm-judge]
                     [--engine ga|gepa]
                     [--capture-trace] [--gepa-budget light|medium|heavy]
                     [--reflection-model MODEL]
gemini-evolve evolve-all --type instructions|commands|skills [--apply]
gemini-evolve trigger watch [--dir PATH] [--debounce FLOAT] [--type TYPE] [--apply]
gemini-evolve trigger cron-install [--interval N] [--type TYPE] [--apply]
gemini-evolve trigger cron-status
gemini-evolve trigger cron-remove
gemini-evolve trigger hook-install [REPO]
gemini-evolve trigger hook-remove [REPO]
```

引擎差异：

- `gepa`（默认）—— `gemini_evolve/gepa_evolve.py` 里的 DSPy + GEPA 反思式优化。带反思（reflection），同样的调用预算下通常质量更高。
- `ga` —— `gemini_evolve/evolve.py` 中内置的锦标赛式遗传循环。更轻量，没有 DSPy 依赖开销。`--engine ga` 切换。
- `evolve-all` 同样支持 `--engine`，默认也是 `gepa`。

实现细节：变体评测会调用 `gemini -p ... -o json --approval-mode plan`，并从 stdout 里解析第一段 JSON，避免 MCP 警告把分数弄坏。plan 模式本来就不执行工具，因此默认**不再加 `--sandbox`**，每次调用省 5–20s。

---

## 配置

代码读取的环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `GEMINI_EVOLVE_HOME` | `~/.gemini` | Gemini 主目录，用于定位目标与挖掘会话 |
| `GEMINI_EVOLVE_MUTATOR_MODEL` | `gemini-3-flash-preview` | 生成变体 |
| `GEMINI_EVOLVE_JUDGE_MODEL` | `gemini-3.1-pro-preview` | LLM judge 打分 |
| `GEMINI_EVOLVE_POPULATION` | `4` | 种群规模 |
| `GEMINI_EVOLVE_GENERATIONS` | `5` | 代数 |
| `GEMINI_EVOLVE_OUTPUT` | `output` | 结果目录 |
| `GEMINI_EVOLVE_PROJECT_PATHS` | `~/ws:~/projects:~/code` | 项目 `.gemini/GEMINI.md` 的扫描根目录 |

> **你的 Gemini 账号没有 preview 模型权限？** 把这两个环境变量改成任何 `gemini -m <model> -p hi` 能跑通的名字即可，例如 `export GEMINI_EVOLVE_MUTATOR_MODEL=gemini-2.5-flash`、`export GEMINI_EVOLVE_JUDGE_MODEL=gemini-2.5-pro`。

---

## 开发

```bash
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/pytest -q
```

架构与模块清单：[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)。运维手册：[docs/RUNBOOK.md](docs/RUNBOOK.md)。贡献：[docs/CONTRIB.md](docs/CONTRIB.md)。

---

## 许可证

MIT —— 见 [LICENSE](LICENSE)。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LichAmnesia/gemini-evolve&type=Date)](https://www.star-history.com/#LichAmnesia/gemini-evolve&Date)
