### 一、项目概述

- `asset_mgnt_report` 用于生成资产管理周报相关数据，覆盖 CPI、GDP、利率、利差、汇率、股票权益、债券、商品与贵金属、数字货币，以及二级市场补充报表。
- 项目已经工程化为三层：
  - 根目录工程配置：保留 Docker、依赖、说明文档和版本控制配置
  - `scripts/`：正式脚本入口、资产管线脚本、校验脚本
  - `src/asset_mgnt_report/`：统一配置、共享算法、运行调度、Web UI
- 运行输出默认写入 `output/`，便于复核、对比和二次加工。

### 二、前置准备

#### 1. Python 依赖

- 安装依赖：

```powershell
pip install -r requirements.txt
```

#### 2. FRED_API_KEY

- 部分脚本需要从 FRED 获取数据，请先配置环境变量 `FRED_API_KEY`
- 申请地址： [FRED_API_KEYS](https://fredaccount.stlouisfed.org/apikeys)

PowerShell 临时设置示例：

```powershell
$env:FRED_API_KEY="your_fred_api_key"
```

#### 3. 手动准备的数据文件

主要通过 AKShare、yfinance、FRED 和官方统计接口自动获取数据，但仍有少量数据需要提前下载并放入 `data/seeds/`。

> 已设置文件名正则匹配，更新文件后通常不需要改代码

- 香港 CPI：[政府統計處 : 表510-60001：消費物價指數](https://www.censtatd.gov.hk/tc/web_table.html?full_series=1&id=510-60001#)
  - 当前主流程优先使用香港统计处 API 自动拉取
  - 本地 `Table 510*.xlsx` 仅作为 API 失败时的兜底种子文件
  - 如需手工准备，仍建议选择“完整数列”，下载长周期完整数据
![CPI_HK 获取图](docs/assets/CPI_HK.png)

- 恒生指数成分股：[指數及成份股 - 指數成份股 - 恆生指數](http://www.aastocks.com/tc/stocks/market/index/hk-index-con.aspx?index=HSI)
![HSI_CAP 获取图](docs/assets/HSI_CAP.png)

- 美国财政部流通国债总票面价值：[U.S. Treasury Monthly Statement of the Public Debt (MSPD)](https://fiscaldata.treasury.gov/datasets/monthly-statement-public-debt/summary-of-treasury-securities-outstanding)
![MSPD获取图](docs/assets/MSPD.png)

- 沪深300成分股名录：[沪深300指数 (000300)](https://www.csindex.com.cn/uploads/file/autofile/cons#/indices/family/detail?indexCode=000300)
![HS300_list获取图](docs/assets/HS300_list.png)

#### 4. “整体”表格准备

- 先运行 `scripts/main.py`
- 再运行 `scripts/gainer.py`
- 最后运行 `scripts/overall.py`
- `scripts/overall.py` 会自动把主报表与 Gainer 的标准化快照回填到 `data/seeds/整体.xlsx`，再输出 `output/整体_processed.xlsx`
- `data/seeds/整体.xlsx` 中房地产等非自动托管行仍保留人工维护；自动流程只覆盖股票权益、债券固收、商品与贵金属（黄金）、数字货币（BTC）、汇率表和 `Gainer` 列
- `scripts/房地产-半自动化表格.xlsx` 是房地产板块的人工整理辅助表，不参与自动脚本直接读取，但属于当前周报工作流的配套输入模板，使用时不要删除或归档到不可见位置

整体表格整理示例：
![整体表格整理示例](docs/assets/整体_处理前.png)

### 三、使用方法

#### 1. 本地 Python 运行

- 统一入口脚本：

```powershell
python scripts/main.py
```

- 统一 Gainer 入口：

```powershell
python scripts/gainer.py
```

- 运行整体表：

```powershell
python scripts/overall.py
```

- 运行二级市场补充报表：

```powershell
python -m scripts.pipelines.secondary_market_report
```

#### 2. 四种运行方式

当前 `scripts/pipelines/` 下的 `*_report.py` 与 `gainer_*.py` 已统一支持以下四种运行方式：

1. CLI 单独运行
2. Web UI 触发
3. `main.py` / `gainer.py` 统一调度
4. Spyder 控制台运行（通过脚本顶部 `CONFIG` 先设参数，再直接运行）

说明：

- 对大多数脚本，CLI 单独运行既支持 `python scripts/pipelines/xxx.py`，也支持通过命令行参数覆盖关键输入。
- `precious_metals_report.py` 当前也支持单独 CLI 运行、Web UI、统一调度和 Spyder，但它的 CLI 入口仍是“直接执行脚本”风格，暂未单独暴露 argparse 参数。
- `main.py` 与 `gainer.py` 本身也已统一为：顶部 `CONFIG` + 环境变量 + CLI 参数 三层配置入口。

示例：

- 主报表统一入口：

```powershell
python scripts/main.py --modules gdp bonds --bond-date 2026-03-27
```

- Gainer 统一入口：

```powershell
python scripts/gainer.py --modules gold btc --current-date 2026-04-11 --previous-date 2026-03-28
```

- 单独运行债券周报：

```powershell
python scripts/pipelines/bond_report.py --start-date 2026-03-15 --end-date 2026-03-28
```

- 单独运行股票 Gainer：

```powershell
python scripts/pipelines/gainer_stock.py --old-date 2026-03-28 --new-date 2026-04-11 --markets CN US
```

#### 3. 参数配置

参数配置有三层优先级，从高到低依次为：

1. 函数显式参数 / CLI 参数
2. 环境变量
3. 入口脚本顶部的 `CONFIG`
4. `src/asset_mgnt_report/config/defaults.py` 中的默认配置

##### 3.1 代码顶部 `CONFIG` 的填写格式

适用于 Spyder 直接运行：先改脚本顶部 `CONFIG`，再运行脚本。

通用格式约定：

- 日期：
  - 统一优先使用 `YYYY-MM-DD`
  - 例如：`2026-03-27`
  - 不要写成 `2026.03.27`
- 日期区间：
  - 分别填 `start_date` 和 `end_date`
  - 例如：`2026-03-15` 到 `2026-03-28`
- 布尔值：
  - 使用 `True` / `False`
- 列表：
  - Python 列表字面量
  - 例如：`["CN", "US"]`
- 数值：
  - 直接写数字
  - 例如黄金价格：`3240.5`
- 路径：
  - 可以写 `Path(...)`，也可以写字符串
  - 相对路径默认相对项目根目录

常用入口脚本的 `CONFIG` 含义：

| 脚本 | `CONFIG` 字段 | 填写格式 |
| --- | --- | --- |
| `scripts/main.py` | `debug` | `True` / `False` |
| `scripts/main.py` | `modules` | 列表；候选值：`cpi`、`gdp`、`interest_rate`、`carry_trade`、`stock_index`、`currency`、`precious_metals`、`bonds`、`crypto` |
| `scripts/main.py` | `stock_markets` | 列表；候选值：`"CN"`、`"US"`、`"HK"` |
| `scripts/main.py` | `bond_date` / `bond_start_date` / `bond_end_date` | 日期字符串：`YYYY-MM-DD` 或 `YYYYMMDD` |
| `scripts/main.py` | `bond_write_history` / `bond_update_snapshot` | `True` / `False`；`bond_write_history=True` 时额外生成 `output/bonds_YYYYMMDD.xlsx` |
| `scripts/gainer.py` | `current_date` / `previous_date` | 日期字符串：`YYYY-MM-DD`；两者都应为周六 |
| `scripts/gainer.py` | `current_gold_price` / `previous_gold_price` | 浮点数，单位 `USD/oz` |
| `scripts/gainer.py` | `modules` | 列表；候选值：`stocks`、`bonds`、`gold`、`btc` |
| `scripts/gainer.py` | `stock_markets` | 列表；候选值：`"CN"`、`"US"`、`"HK"` |
| `scripts/gainer.py` | `output_path` | 路径字符串或 `Path(...)` |
| `scripts/overall.py` | `input_path` / `output_path` / `log_path` | 路径字符串或 `Path(...)` |

单脚本 `CONFIG` 也已补注释，直接看脚本顶部即可。常见示例：

| 脚本 | 常用字段 | 填写格式 |
| --- | --- | --- |
| `bond_report.py` | `bond_date` / `start_date` / `end_date` | `YYYY-MM-DD` 或 `YYYYMMDD` |
| `secondary_market_report.py` | `market_mode` | `us` / `china` / `hk` / `mixed` |
| `secondary_market_report.py` | `start_date` / `end_date` | `YYYY-MM-DD` |
| `stock_index_report.py` | `time_range` | 整数天数，如 `30`、`365`、`2920` |
| `gainer_stock.py` | `old_date` / `new_date` | `YYYY-MM-DD` |
| `gainer_stock.py` | `markets` | 列表；候选值：`"CN"`、`"US"`、`"HK"` |
| `gainer_bond.py` | `target_date` | `YYYY-MM-DD` |
| `gainer_btc.py` | `old_date` / `new_date` | `YYYY-MM-DD` |
| `gainer_gold.py` | `current_price` / `previous_price` | 浮点数，单位 `USD/oz` |
| 其余报表脚本 | `debug` | `True` / `False` |

##### 3.2 CLI 参数说明

下表只列“显式支持的 CLI 参数”。
其中 `precious_metals_report.py` 目前支持直接 CLI 运行，但没有单独暴露 argparse 参数。

| 脚本 | 支持参数 | 参数格式 |
| --- | --- | --- |
| `scripts/main.py` | `--debug` | 开关参数 |
| `scripts/main.py` | `--modules` | 空格分隔列表；候选值同上，如 `--modules gdp bonds` |
| `scripts/main.py` | `--stock-markets` | 空格分隔列表；如 `--stock-markets CN US` |
| `scripts/main.py` | `--bond-date` | `YYYY-MM-DD` 或 `YYYYMMDD` |
| `scripts/main.py` | `--bond-start-date` / `--bond-end-date` | `YYYY-MM-DD` 或 `YYYYMMDD` |
| `scripts/main.py` | `--bond-write-history` | 开关参数；额外生成 `output/bonds_YYYYMMDD.xlsx` |
| `scripts/main.py` | `--bond-skip-snapshot-update` | 开关参数 |
| `scripts/gainer.py` | `--current-date` / `--previous-date` | `YYYY-MM-DD`；两者都应为周六 |
| `scripts/gainer.py` | `--current-gold-price` / `--previous-gold-price` | 浮点数 |
| `scripts/gainer.py` | `--modules` | 空格分隔列表；候选值：`stocks bonds gold btc` |
| `scripts/gainer.py` | `--stock-markets` | 空格分隔列表；如 `--stock-markets CN HK` |
| `scripts/gainer.py` | `--output-path` | 路径字符串 |
| `bond_report.py` | `--debug` | 开关参数 |
| `bond_report.py` | `--bond-date` | `YYYY-MM-DD` 或 `YYYYMMDD` |
| `bond_report.py` | `--start-date` / `--end-date` | `YYYY-MM-DD` 或 `YYYYMMDD` |
| `bond_report.py` | `--write-history` | 开关参数；额外生成 `output/bonds_YYYYMMDD.xlsx` |
| `bond_report.py` | `--skip-snapshot-update` | 开关参数 |
| `carry_trade_report.py` | `--debug` | 开关参数 |
| `cpi_report.py` | `--debug` | 开关参数 |
| `crypto_report.py` | `--debug` | 开关参数 |
| `crypto_report.py` | `--end-date` | `YYYY-MM-DD` |
| `fx_report.py` | `--debug` | 开关参数 |
| `gainer_bond.py` | `--target-date` | `YYYY-MM-DD` |
| `gainer_btc.py` | `--old-date` / `--new-date` | `YYYY-MM-DD` |
| `gainer_gold.py` | `--current-price` / `--previous-price` | 浮点数 |
| `gainer_stock.py` | `--old-date` / `--new-date` | `YYYY-MM-DD` |
| `gainer_stock.py` | `--markets` | 空格分隔列表；候选值：`CN US HK` |
| `gdp_report.py` | `--debug` | 开关参数 |
| `interest_rate_report.py` | `--debug` | 开关参数 |
| `secondary_market_report.py` | `--market-mode` | `us` / `china` / `hk` / `mixed` |
| `secondary_market_report.py` | `--use-default-dates` | 开关参数 |
| `secondary_market_report.py` | `--start-date` / `--end-date` | `YYYY-MM-DD` |
| `stock_cap_report.py` | `--markets` | 空格分隔列表；候选值：`CN US HK` |
| `stock_index_report.py` | `--time-range` | 整数天数 |
| `stock_index_report.py` | `--debug` | 开关参数 |
| `stock_index_report.py` | `--stock-markets` | 空格分隔列表；候选值：`CN US HK` |

CLI 示例：

```powershell
python scripts/main.py --modules gdp bonds --bond-date 2026-03-27
python scripts/gainer.py --modules gold btc --current-date 2026-04-11 --previous-date 2026-03-28
python scripts/pipelines/bond_report.py --start-date 2026-03-15 --end-date 2026-03-28
python scripts/pipelines/gainer_stock.py --old-date 2026-03-28 --new-date 2026-04-11 --markets CN US
```

##### 3.3 统一调度入口支持范围

统一调度入口分两类：

`scripts/main.py` 的模块映射：

| 模块名 | 对应脚本 |
| --- | --- |
| `cpi` | `scripts/pipelines/cpi_report.py` |
| `gdp` | `scripts/pipelines/gdp_report.py` |
| `interest_rate` | `scripts/pipelines/interest_rate_report.py` |
| `carry_trade` | `scripts/pipelines/carry_trade_report.py` |
| `stock_index` | `scripts/pipelines/stock_index_report.py` |
| `currency` | `scripts/pipelines/fx_report.py` |
| `precious_metals` | `scripts/pipelines/precious_metals_report.py` |
| `bonds` | `scripts/pipelines/bond_report.py` |
| `crypto` | `scripts/pipelines/crypto_report.py` |

`scripts/gainer.py` 的模块映射：

| 模块名 | 对应脚本 |
| --- | --- |
| `stocks` | `scripts/pipelines/gainer_stock.py` |
| `bonds` | `scripts/pipelines/gainer_bond.py` |
| `gold` | `scripts/pipelines/gainer_gold.py` |
| `btc` | `scripts/pipelines/gainer_btc.py` |

 | 入口脚本 | 调度范围 | 支持参数 | 参数格式 |
 | --- | --- | --- | --- |
| `scripts/main.py` | 主报表模块：`cpi`、`gdp`、`interest_rate`、`carry_trade`、`stock_index`、`currency`、`precious_metals`、`bonds`、`crypto` | `debug` | `True` / `False` 或 `--debug` |
| `scripts/main.py` | 同上 | `modules` | 列表或 CLI 空格分隔列表 |
| `scripts/main.py` | 仅 `stock_index` 子链路 | `stock_markets` | `["CN", "US"]` 或 `--stock-markets CN US` |
| `scripts/main.py` | 仅 `bonds` 子链路 | `bond_date` | `YYYY-MM-DD` / `YYYYMMDD` |
| `scripts/main.py` | 仅 `bonds` 子链路 | `bond_start_date` / `bond_end_date` | `YYYY-MM-DD` / `YYYYMMDD` |
| `scripts/main.py` | 仅 `bonds` 子链路 | `bond_write_history` / `bond_update_snapshot` | `True` / `False` 或开关参数；历史补录文件直接写入 `output/` |
| `scripts/gainer.py` | Gainer 子链路：`stocks`、`bonds`、`gold`、`btc` | `modules` | 列表或 CLI 空格分隔列表 |
| `scripts/gainer.py` | 仅 `stocks` 子链路 | `stock_markets` | `["CN", "HK"]` 或 `--stock-markets CN HK` |
| `scripts/gainer.py` | 统一日期输入 | `current_date` / `previous_date` | `YYYY-MM-DD`；两者都应为周六 |
| `scripts/gainer.py` | 仅 `gold` 子链路 | `current_gold_price` / `previous_gold_price` | 浮点数，单位 `USD/oz` |
| `scripts/gainer.py` | 输出路径 | `output_path` | 路径字符串或 `Path(...)` |

环境变量适合 Docker 和自动化场景，常用项包括：

- `AMR_DEBUG`
- `AMR_USE_PROXY`
- `AMR_HTTP_PROXY`
- `AMR_HTTPS_PROXY`
- `FRED_API_KEY`
  - 用于美国 GDP、利率、CPI、核心 PCE 等官方 FRED 序列
- `AMR_MAIN_MODULES`
- `AMR_MAIN_STOCK_MARKETS`
- `AMR_MAIN_BOND_DATE`
- `AMR_MAIN_BOND_START_DATE`
- `AMR_MAIN_BOND_END_DATE`
- `AMR_MAIN_BOND_WRITE_HISTORY`
- `AMR_MAIN_BOND_UPDATE_SNAPSHOT`
- `AMR_GAINER_CURRENT_DATE`
- `AMR_GAINER_PREVIOUS_DATE`
- `AMR_GAINER_MODULES`
- `AMR_GAINER_STOCK_MARKETS`
- `AMR_GAINER_OUTPUT_PATH`
- `AMR_GOLD_CURRENT_PRICE`
- `AMR_GOLD_PREVIOUS_PRICE`

#### 4. Web UI 运行

- 启动方式：

```powershell
streamlit run scripts/web_ui.py
```

- 默认访问地址：
  - `http://localhost:8501`

- Web UI 可用于：
  - 通过顶部标签在主页、主报表、Gainer、整体表、校验五个工作区之间切换
  - 默认启用代理模式，也可在侧边栏关闭
  - 在主页概览中同时查看四个工作入口
  - 选择主报表模块
  - 在页面内通过日历选择 Gainer 的 `本周末日期（周六）` 和 `两周前日期（周六）`
  - 参考 LBMA Gold Price 页面中的 `USD PM` 填写黄金价格
  - 在页面内指定整体表输入、输出、日志路径
  - 在当前标签页内保留运行结果，不再因工作区切换出现空白页
  - 触发 main / codex 输出校验

#### 5. Docker 运行

- 构建镜像：

```powershell
docker build -t asset-mgnt-report .
```

- 启动 Web UI：

```powershell
docker compose up amr-ui
```

- 在容器中运行主报表：

```powershell
docker compose run --rm amr-cli python -m scripts.main
```

- 在容器中运行校验：

```powershell
docker compose run --rm amr-cli python -m scripts.validation.validate_outputs
```

更完整的 Docker 说明见：
- `docs/docker部署与使用指南.md`
- `docs/版本迭代日志.md`

#### 6. 输出位置

- 主输出目录：`output/`
- 原始调试数据：`output/raw_data/`
- main / codex 对比报告：`docs/重构前后对比报告.md`

### 四、项目结构

- `scripts/main.py`：主报表入口
- `scripts/gainer.py`：Gainer 入口
- `scripts/overall.py`：整体表入口
- `scripts/web_ui.py`：Web UI 启动入口
- `scripts/pipelines/`：各资产大类与报表脚本
- `scripts/validation/`：回归与对比校验脚本
- `src/asset_mgnt_report/`
  - `config/`：统一配置与环境变量解析
  - `metrics/`：统一收益率、年化、波动率、Sharpe 算法
  - `io/`：路径和输入输出辅助
  - `services/`：脚本调度、结果校验
  - `ui/`：Streamlit Web UI
- `data/seeds/`：纳入版本控制的种子数据
- `data/local/`：本地临时输入，不纳入版本控制
- `output/`：运行输出
- `archive/legacy_code/`：历史脚本归档
- `archive/legacy_code/stock_us_cn_hk/`：原二级市场独立目录归档与历史产物留档
- `docs/assets/`：Readme 与文档使用的静态图片
- `docs/`：说明文档、版本日志与对比报告

### 五、输出文件说明

| 指标模块 | 来源脚本 | 输出文件名 |
| --- | --- | --- |
| CPI | `scripts/pipelines/cpi_report.py` | `cpi_metrics.xlsx`、`cpi_trends.png` |
| GDP | `scripts/pipelines/gdp_report.py` | `gdp_metrics.xlsx` |
| 利率 | `scripts/pipelines/interest_rate_report.py` | `interest_rate_metrics.xlsx`、`interest_rate_trend_2y.png` |
| 利差 | `scripts/pipelines/carry_trade_report.py` | `currency_spreads.png` |
| 汇率 | `scripts/pipelines/fx_report.py` | `fx_metrics.xlsx` |
| 股票权益 | `scripts/pipelines/stock_index_report.py`、`scripts/pipelines/stock_cap_report.py` | `stock_weekly_report.xlsx` |
| 债券 | `scripts/pipelines/bond_report.py` | `bonds.xlsx` |
| 商品与贵金属 | `scripts/pipelines/precious_metals_report.py` | `commodity_indicators_summary.xlsx` |
| 数字货币 | `scripts/pipelines/crypto_report.py` | `crypto_metrics.xlsx` |
| Gainer | `scripts/gainer.py` | `Gainer.xlsx` |
| 整体 | `scripts/overall.py` | `整体_processed.xlsx`（运行时会同步维护 `data/seeds/整体.xlsx` 与 `output/raw_data/overall_seed_snapshot.json`） |
| 二级市场 | `scripts/pipelines/secondary_market_report.py` | `us_market_report_*.xlsx`、`china_market_report_*.xlsx`、`hk_market_report_*.xlsx`、`mixed_market_report_*.xlsx` |

### 六、数据获取及计算方法

#### 1. 统一指标口径

- 日频可投资资产统一先计算 `pct_change()` 日收益率
- 年化收益率统一通过 `src/asset_mgnt_report/metrics/annualization.py`
- 年化波动率统一通过 `src/asset_mgnt_report/metrics/volatility.py`
- Sharpe / Adjusted Sharpe 统一通过 `src/asset_mgnt_report/metrics/sharpe.py`
- 地区无风险利率统一配置：
  - `US = 0.045`
  - `CN = 0.017`
  - `HK = 0.0062`

#### 1.1 汇率数据源策略

- 汇率模块主源仍为 AkShare 的 `forex_hist_em`
- 若 Eastmoney 抓取失败，会按顺序降级到：
  - `yfinance`
  - AkShare 官方人民币历史接口：`currency_boc_safe`
  - AkShare 官方人民币历史接口：`currency_boc_sina`
  - 本地缓存
- `fx_metrics.xlsx` 会写出 `数据源` 字段，标记本次汇率指标来自主源、备用源、官方降级源或缓存

#### 2. CPI

| 地区 | 数据类型 | 数据源说明 |
| --- | --- | --- |
| 美国 | CPI 指数 / MoM / YoY | FRED 官方序列 `CPIAUCSL`，本地由指数计算 MoM / YoY |
| 美国 | 核心 PCE 指数 / MoM / YoY | FRED 官方序列 `PCEPILFE`，本地由指数计算 MoM / YoY |
| 中国 | CPI 指数 / MoM / YoY | 国家统计局官方链路优先；若本机受 WAF 限制，则自动回退到 `akshare.macro_china_cpi()` |
| 香港 | CPI 指数 / MoM / YoY | 香港统计处 API 优先；本地 Excel：`data/seeds/Table 510-60001_tc.xlsx` 仅作兜底 |

- 中国 CPI 不再主用滞后的 `macro_china_cpi_monthly()` / `macro_china_cpi_yearly()` Jin10 接口。
- 若中国国家统计局官方站点在当前网络环境中返回 403 或非 JSON，脚本会自动切换到 AkShare 官方文档中明确存在的 `macro_china_cpi()`。
- `cpi_metrics.xlsx` 会写出 `数据源` 列，便于区分 `fred`、`china_nbs`、`china_akshare_macro_china_cpi`、`hk_censtatd_api` 和香港本地种子兜底。

$$
\text{CAGR} = \left( \prod_{i=1}^{n} \left(1 + \frac{r_i}{100} \right) \right)^{\frac{1}{n}} - 1
$$

#### 3. GDP

| 区域 | 数据 | 数据来源 |
| --- | --- | --- |
| 美国 | YoY(%) | `akshare.macro_usa_gdp_monthly()` |
| 美国 | 当前季度 GDP | `fred.get_series('NGDPSAXDCUSQ')` |
| 美国 | 当前年化 GDP | `FRED API`：`series_id='GDP'` |
| 中国 | YoY(%) | `akshare.macro_china_gdp_yearly()` |
| 中国 | 当前季度 GDP | `akshare.macro_china_gdp()`，计算季度差分 |
| 中国 | 当前年化 GDP | 最近四个季度 GDP 差分求和 |
| 香港 | YoY(%) | `akshare.macro_china_hk_gbp_ratio()` |
| 香港 | 当前季度 GDP | `akshare.macro_china_hk_gbp()` |
| 香港 | 当前年化 GDP | 最近四个季度 GDP 求和 |

#### 4. 利率与利差

- 利率：
  - 美国：Federal Fund Rate
  - 中国：LPR、Chibor
  - 香港：HIBOR
- 利差：
  - `CNH - USD`
  - `HKD - USD`
  - `CNH - HKD`

MoM、YoY 算法均使用共享容忍窗口逻辑。

#### 5. 汇率

| 汇率 | 数据来源 |
| --- | --- |
| USD/CNH | `akshare.forex_hist_em()` |
| USD/HKD | `akshare.forex_hist_em()` |
| CNH/HKD | 由 USD/CNH 与 USD/HKD 跨式计算 |

#### 6. 股票权益

| 市场 | 指数名称 | 数据来源 |
| --- | --- | --- |
| 美国 | S&P 500 | `ak.index_us_stock_sina(symbol=".inx")` |
| 中国 | 沪深300 | `ak.stock_zh_index_daily("sh000300")` |
| 香港 | 恒生指数 | `ak.stock_hk_index_daily_sina("HSI")` |

- 年化收益率统一使用共享函数，不再区分“短期算术、长期几何”的分裂实现
- 年化波动率统一为：

$$
\sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}
$$

- Sharpe Ratio 统一为：

$$
\text{Sharpe Ratio} = \frac{r_{\text{ann}} - r_f}{\sigma_{\text{ann}}}
$$

#### 7. 债券

**中国国债**

| 指标类型 | 数据项 | 数据来源 |
| --- | --- | --- |
| 总市值 | 国债托管面值 | `ak.bond_cash_summary_sse(date=...)` |
| 交易量 | 记账式国债当日成交金额 | `ak.bond_deal_summary_sse(date=...)` |
| 收益率 | 2年、10年期国债收益率 | `ak.bond_zh_us_rate()` |

**美国国债**

| 指标类型 | 数据项 | 数据来源 |
| --- | --- | --- |
| 总市值 | 国债总额 | `fred.get_series('GFDEBTN')` |
| 收益率 | 2年、10年期国债收益率 | `pandas_datareader.data.DataReader()` |

#### 8. 商品与贵金属

| 标的代码 | 品类 | 数据来源 |
| --- | --- | --- |
| GLD | 黄金 ETF | `yfinance.Ticker("GLD").history(period="6y")` |
| CL=F | 原油期货 | `yfinance.Ticker("CL=F").history(period="6y")` |
| HG=F | 铜期货 | `yfinance.Ticker("HG=F").history(period="6y")` |

#### 9. 整体

- 波动率和 Sharpe Ratio 统一使用月度数据
- `Adjusted Sharpe` 统一通过共享函数计算
- 汇率修正逻辑仍保留，但实现已收敛到统一算法层

### 七、Docker 与 Web UI

- Docker 适合：
  - 跨设备迁移
  - 给不会 Python 的协作者直接使用
  - 固定依赖环境，减少“我这里能跑、别人那里不能跑”
- Web UI 适合：
  - 在页面中勾选模块
  - 不直接改代码
  - 运行主报表 / Gainer / 整体 / 校验

建议阅读：
- `docs/docker部署与使用指南.md`
- `docs/版本迭代日志.md`
- `docs/重构前后对比报告.md`
