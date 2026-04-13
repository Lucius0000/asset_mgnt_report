# Asset Management Report Working Rules

## 代码风格
- 优先复用 `src/asset_mgnt_report/metrics` 中的统一计算函数。
- 新增逻辑优先写入 `src/asset_mgnt_report/`，根目录脚本仅保留兼容入口。
- 对外部数据源读取失败时优先记录日志并继续其他模块，不中断全流程。

## 目录职责
- `src/asset_mgnt_report/`：核心实现
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
