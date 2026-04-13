# Asset Management Report Working Rules

## 代码风格
- 优先复用 `src/asset_mgnt_report/metrics` 中的统一计算函数。
- 新增逻辑优先写入 `src/asset_mgnt_report/`，根目录脚本仅保留兼容入口。
- 对外部数据源读取失败时优先记录日志并继续其他模块，不中断全流程。

## 目录职责
- `src/asset_mgnt_report/`：核心实现
- `scripts/`：入口脚本、流程脚本、工具脚本
- `data/seeds/`：版本控制的种子数据
- `data/local/`：本地临时输入，不纳入版本控制
- `output/`：生成产物，不纳入版本控制
- `archive/legacy_code/`：历史代码归档

## 浏览器实测
- 只要任务涉及本机浏览器真实点击、localhost 页面回归、白屏复现、按钮是否可点、或用户明确要求“实际在浏览器里测试”，优先使用 `local-edge-gui` skill。
- 默认 skill 路径：`C:\Users\Lucius\.codex\skills\local-edge-gui`
- 默认脚本路径：`C:\Users\Lucius\.codex\skills\local-edge-gui\scripts\local_edge_gui.py`
- 优先用 `expect=...` + `click=...` + `shot=...` 的步骤式验证，不要只依赖静态代码阅读、Streamlit AppTest 或 DOM 抓取结果。
- 浏览器实测截图默认输出到当前仓库的 `output/playwright/`
- 如果页面修复依赖浏览器交互验证，最终说明里要写明实际执行过的步骤和产出的截图文件。

## Spyder 与换行符
- `scripts/` 下的 Python 脚本统一使用 LF，禁止混用 `CRLF` 与 `LF`，否则 Spyder 会提示“当前脚本文件使用了多个换行符”。
- `codex` 根目录关键文档也统一使用 LF，至少包括 `AGENTS.md`、`Readme.md`、`docs/*.md`、`.gitignore`、`.gitattributes`、`pyproject.toml`、`requirements*.txt`、`compose.yaml`、`Dockerfile`。
- 只要修改过 `scripts/` 下的 `.py` 文件，在提交前必须运行 `python scripts/tools/normalize_line_endings.py --quiet` 检查。
- 如果检查发现混用换行符，立刻运行 `python scripts/tools/normalize_line_endings.py --write` 统一修复，再重新检查一次。
- 如果修改了根目录文档或配置文件，提交前要确认这些文本文件也保持单一 LF；不要依赖编辑器自动转换。
- 将本仓库同步到 `wealth-hunter` 之后，必须在目标仓库的 `asset_mgnt_report` 目录再执行一次同样的检查与修复，因为复制工具会原样保留文件字节内容。
- 以仓库内的 `.gitattributes` 和 `scripts/tools/normalize_line_endings.py` 的检查结果为准。

## 环境变量
- `FRED_API_KEY`
- `AMR_DEBUG`
- `AMR_USE_PROXY`
- `AMR_HTTP_PROXY`
- `AMR_HTTPS_PROXY`
- `AMR_GAINER_CURRENT_DATE`
- `AMR_GAINER_PREVIOUS_DATE`
- `AMR_GOLD_CURRENT_PRICE`
- `AMR_GOLD_PREVIOUS_PRICE`

## 提交要求
- 每次业务修改同步更新 `docs/版本迭代日志.md`
- 所有新指标逻辑必须附带至少一个测试或验证脚本
- 合并前运行 `pytest`
