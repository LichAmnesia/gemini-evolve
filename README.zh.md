# gemini-evolve

[English](README.md) | 简体中文

`gemini-evolve` 通过调用 Gemini CLI 自身来变异候选方案、针对评测任务打分、并只在通过硬性门槛时才应用变更，从而不断优化 Gemini CLI 的指令类工件（instructions / commands / skills）。

- 不直接使用 Gemini SDK/API。
- 所有模型调用都经由 `gemini -p ... -o json`。
- 文档：[架构](docs/CODEMAPS/INDEX.md)、[贡献](docs/CONTRIB.md)、[运维手册](docs/RUNBOOK.md)

## 安装

```bash
cd ~/ws/gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"

./.venv/bin/gemini-evolve --version
gemini --version
```

若已激活 venv，可省略 `./.venv/bin/` 前缀。

GEPA/DSPy 引擎已内置于默认依赖，无需额外安装。

## 快速上手

1. 选择要进化的目标。

```bash
mkdir -p ~/.gemini
test -f ~/.gemini/GEMINI.md || printf '# Gemini Instructions\n' > ~/.gemini/GEMINI.md

./.venv/bin/gemini-evolve discover --type instructions
```

2. 仅校验约束（不落盘）。

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
```

3. 跑一次小规模 review。

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md -g 2 -p 2
```

4. 查看产物。

```bash
find output -maxdepth 3 -type f | sort
cat output/global/$(ls -t output/global | head -1)/metrics.json
```

5. 信任循环后再真正写回。

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

`--apply` 成功时，会在覆盖前把原文件备份为 `GEMINI.md.<UTC 时间戳>.bak`。

可选的 GEPA 流程：

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --engine gepa --capture-trace --gepa-budget light
```

## 支持进化的目标

| 目标 | 路径模式 | 作用范围 |
| --- | --- | --- |
| 全局 instructions | `~/.gemini/GEMINI.md` | 所有 Gemini CLI 会话 |
| 项目 instructions | `<project>/.gemini/GEMINI.md` | 单个项目 |
| Commands | `~/.gemini/commands/*.toml` | 自定义斜杠命令 |
| Skills | `~/.gemini/skills/**/*.md` | Skill 定义 |

项目级 instructions 默认扫描 `~/ws`、`~/projects`、`~/code`，可通过 `GEMINI_EVOLVE_PROJECT_PATHS=/path/a:/path/b` 覆盖。

## 进化主循环

```text
目标文件
  -> 构建评测数据集
  -> 校验 baseline 约束
  -> 通过 gemini CLI 生成 N 个变体
  -> 在 sandbox/plan 模式下评测变体
  -> 锦标赛选择 + 可选交叉
  -> holdout 与 baseline 对比
  -> 保存至 output/<target>/<timestamp>/
  -> 可选地写回源文件
```

入口文件：

- [gemini_evolve/cli.py](gemini_evolve/cli.py)
- [gemini_evolve/evolve.py](gemini_evolve/evolve.py)
- [gemini_evolve/gepa_evolve.py](gemini_evolve/gepa_evolve.py)
- [gemini_evolve/dspy_adapter.py](gemini_evolve/dspy_adapter.py)
- [gemini_evolve/cli_runner.py](gemini_evolve/cli_runner.py)

## 评测数据来源

| 来源 | 参数 | 数据本体 |
| --- | --- | --- |
| 合成 | `--eval-source synthetic` | 由当前 instructions 让 Gemini 生成的测试场景 |
| 会话 | `--eval-source session` | `~/.gemini/tmp/*/chats/session-*.json` 中的用户消息 |
| 黄金集 | `--eval-source golden --eval-dataset data.jsonl` | 人工整理的 JSONL 数据集 |

会话挖掘会跳过疑似密钥/凭证的消息。

## 产物与门禁

每次运行都会写出：

- `output/<target_name>/<UTC 时间戳>/baseline.md`
- `output/<target_name>/<UTC 时间戳>/evolved.md`
- `output/<target_name>/<UTC 时间戳>/metrics.json`

`--apply` 仅当下面全部成立时才会写回：

1. 内容非空。
2. 大小不超过对应目标的上限。
3. 增长幅度不超过配置的增长上限。
4. Holdout 改进大于等于 `min_improvement_pct`（默认 `2.0`）。
5. Evolved 内容确实与 baseline 不同。

当前大小上限：

- Instructions：`15KB`
- Skills：`15KB`
- Commands：`5KB`

## 触发自动化

监听已结束的 Gemini 会话：

```bash
./.venv/bin/gemini-evolve trigger watch --apply
```

在 macOS 上安装 launchd 定时任务：

```bash
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
./.venv/bin/gemini-evolve trigger cron-status
./.venv/bin/gemini-evolve trigger cron-remove
```

安装 git post-commit hook：

```bash
./.venv/bin/gemini-evolve trigger hook-install .
./.venv/bin/gemini-evolve trigger hook-remove .
```

仅当提交中命中 `GEMINI.md` 或 `.gemini/` 时才会触发。

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
| `GEMINI_EVOLVE_PROJECT_PATHS` | `~/ws:~/projects:~/code` | 扫描项目 `.gemini/GEMINI.md` 的根目录 |

## 命令总览

```text
gemini-evolve discover --type instructions|commands|skills
gemini-evolve evolve TARGET [--dry-run] [--apply] [-g N] [-p N] [--engine ga|gepa]
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

实现细节：agent 仿真会调用 `gemini -p ... -o json --sandbox --approval-mode plan`，再从 stdout 中解析第一段 JSON，避免 MCP 警告导致评测失败。

引擎差异：

- `ga` —— `gemini_evolve/evolve.py` 中内置的锦标赛式遗传循环。
- `gepa` —— 走 `gemini_evolve/gepa_evolve.py` 里的 DSPy GEPA 优化。
- `evolve-all` —— 目前仅走 GA 路径。

## 开发

```bash
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/pytest -q
```

源码结构：

```text
gemini_evolve/
  cli.py              Click CLI 入口
  evolve.py           主循环、结果保存、apply 逻辑
  gepa_evolve.py      可选的 DSPy GEPA 引擎
  dspy_adapter.py     基于 gemini CLI 的 DSPy LM 适配器
  cli_runner.py       非交互式 gemini CLI 子进程封装
  dataset.py          合成与黄金集处理
  mutator.py          变异与交叉 prompt
  fitness.py          启发式与 LLM judge 评分
  constraints.py      非空、大小、增长门禁
  session_miner.py    真实会话数据集抽取 + 密钥过滤
  json_utils.py       从杂乱 LLM 输出中抽取 JSON
  triggers/           watch / cron / hook 自动化
tests/                解析、约束、hook、数据集、apply 的单元测试
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LichAmnesia/gemini-evolve&type=Date)](https://www.star-history.com/#LichAmnesia/gemini-evolve&Date)

## 许可证

见仓库根目录 LICENSE（如有）。
