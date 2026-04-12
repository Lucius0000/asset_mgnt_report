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
- 每次业务修改同步更新 `版本迭代日志.md`
- 所有新指标逻辑必须附带至少一个测试或验证脚本
- 合并前运行 `pytest`
