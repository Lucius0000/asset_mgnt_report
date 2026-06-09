from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.config.inputs import parse_bool, parse_csv_list, resolve_config_value
from src.asset_mgnt_report.services.progress import JobCancelledError, emit_progress, ensure_not_cancelled
from src.asset_mgnt_report.services.runtime import run_named_pipeline

# 顶部配置区
# - 支持的统一调度模块:
#   cpi -> scripts/pipelines/cpi_report.py
#   gdp -> scripts/pipelines/gdp_report.py
#   interest_rate -> scripts/pipelines/interest_rate_report.py
#   carry_trade -> scripts/pipelines/carry_trade_report.py
#   stock_index -> scripts/pipelines/stock_index_report.py
#   currency -> scripts/pipelines/fx_report.py
#   precious_metals -> scripts/pipelines/precious_metals_report.py
#   bonds -> scripts/pipelines/bond_report.py
#   crypto -> scripts/pipelines/crypto_report.py
# - debug: 布尔值，True / False
# - modules: 列表，候选值为 cpi/gdp/interest_rate/carry_trade/stock_index/currency/precious_metals/bonds/crypto
# - stock_markets: 列表，候选值为 CN/US/HK；仅 stock_index 子链路使用
# - bond_date / bond_start_date / bond_end_date: 字符串，格式 YYYY-MM-DD 或 YYYYMMDD，例如 2026-03-27；仅 bonds 子链路使用
# - bond_write_history / bond_update_snapshot: 布尔值，True / False；仅 bonds 子链路使用
#   bond_write_history=True 时会在 output 根目录额外生成 bonds_YYYYMMDD.xlsx，不会创建 history 子目录
CONFIG = {
    "debug": False,
    "modules": [
        "cpi",
        "gdp",
        "interest_rate",
        "carry_trade",
        "stock_index",
        "currency",
        "precious_metals",
        "bonds",
        "crypto",
    ],
    "stock_markets": ["CN", "US", "HK"],
    "bond_date": None,
    "bond_start_date": None,
    "bond_end_date": None,
    "bond_write_history": False,
    "bond_update_snapshot": True,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

STOCK_MARKET_OPTIONS = ("CN", "US", "HK")


def _configure_shared_yfinance_cache(config) -> None:
    try:
        import yfinance.cache as yf_cache
    except Exception:
        return
    cache_dir = config.raw_output_dir / "yfinance_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf_cache.set_cache_location(str(cache_dir))
    yf_cache.set_tz_cache_location(str(cache_dir))


def _normalize_stock_markets(stock_markets: list[str] | None) -> list[str]:
    selected = stock_markets or CONFIG["stock_markets"]
    normalized = [market.upper() for market in selected if market and market.upper() in STOCK_MARKET_OPTIONS]
    # 保持顺序稳定，避免 UI / CLI 选择顺序影响输出列顺序。
    return [market for market in STOCK_MARKET_OPTIONS if market in normalized]


def _normalize_modules(modules: list[str] | None) -> list[str]:
    selected = modules or CONFIG["modules"]
    allowed = set(CONFIG["modules"])
    normalized = [module for module in selected if module in allowed]
    return normalized or list(CONFIG["modules"])


def main(
    debug: bool | None = None,
    modules: list[str] | None = None,
    stock_markets: list[str] | None = None,
    bond_date: str | None = None,
    bond_start_date: str | None = None,
    bond_end_date: str | None = None,
    bond_write_history: bool = False,
    bond_update_snapshot: bool = True,
    progress_callback=None,
    cancel_check=None,
) -> None:
    resolved_debug = resolve_config_value(
        explicit=debug,
        env_key="AMR_MAIN_DEBUG",
        default=CONFIG["debug"],
        caster=parse_bool,
    )
    resolved_modules = resolve_config_value(
        explicit=modules,
        env_key="AMR_MAIN_MODULES",
        default=CONFIG["modules"],
        caster=parse_csv_list,
    )
    resolved_stock_markets = resolve_config_value(
        explicit=stock_markets,
        env_key="AMR_MAIN_STOCK_MARKETS",
        default=CONFIG["stock_markets"],
        caster=parse_csv_list,
    )
    resolved_bond_date = resolve_config_value(
        explicit=bond_date,
        env_key="AMR_MAIN_BOND_DATE",
        default=CONFIG["bond_date"],
        caster=lambda raw: raw,
    )
    resolved_bond_start_date = resolve_config_value(
        explicit=bond_start_date,
        env_key="AMR_MAIN_BOND_START_DATE",
        default=CONFIG["bond_start_date"],
        caster=lambda raw: raw,
    )
    resolved_bond_end_date = resolve_config_value(
        explicit=bond_end_date,
        env_key="AMR_MAIN_BOND_END_DATE",
        default=CONFIG["bond_end_date"],
        caster=lambda raw: raw,
    )
    resolved_bond_write_history = resolve_config_value(
        explicit=bond_write_history,
        env_key="AMR_MAIN_BOND_WRITE_HISTORY",
        default=CONFIG["bond_write_history"],
        caster=parse_bool,
    )
    resolved_bond_update_snapshot = resolve_config_value(
        explicit=bond_update_snapshot,
        env_key="AMR_MAIN_BOND_UPDATE_SNAPSHOT",
        default=CONFIG["bond_update_snapshot"],
        caster=parse_bool,
    )

    config = build_app_config(overrides={"debug": bool(resolved_debug)})
    _configure_shared_yfinance_cache(config)
    selected_modules = _normalize_modules(resolved_modules)
    selected_stock_markets = _normalize_stock_markets(resolved_stock_markets)
    total_modules = len(selected_modules)
    completed_modules: list[str] = []
    emit_progress(
        progress_callback,
        "job_init",
        total_units=total_modules,
        pending_units=selected_modules,
    )
    for index, module_name in enumerate(selected_modules, start=1):
        ensure_not_cancelled(cancel_check)
        runner_kwargs = {
            "debug": config.debug,
            "progress_callback": progress_callback,
            "cancel_check": cancel_check,
        }
        if module_name == "stock_index":
            runner_kwargs["stock_markets"] = selected_stock_markets
        if module_name == "bonds":
            runner_kwargs["bond_date"] = resolved_bond_date
            runner_kwargs["start_date"] = resolved_bond_start_date
            runner_kwargs["end_date"] = resolved_bond_end_date
            runner_kwargs["write_history"] = bool(resolved_bond_write_history)
            runner_kwargs["update_snapshot"] = bool(resolved_bond_update_snapshot)
        emit_progress(
            progress_callback,
            "module_start",
            module_name=module_name,
            module_index=index,
            total_units=total_modules,
            completed_units=completed_modules,
            pending_units=selected_modules[index - 1 :],
            progress_ratio=(index - 1) / total_modules if total_modules else 0.0,
        )
        try:
            run_named_pipeline(module_name, **runner_kwargs)
        except TypeError:
            try:
                runner_kwargs.pop("cancel_check", None)
                run_named_pipeline(module_name, **runner_kwargs)
            except TypeError:
                try:
                    runner_kwargs.pop("progress_callback", None)
                    run_named_pipeline(module_name, **runner_kwargs)
                except TypeError:
                    run_named_pipeline(module_name)
        except JobCancelledError:
            emit_progress(
                progress_callback,
                "module_error",
                module_name=module_name,
                message="任务已取消",
                completed_units=completed_modules,
                pending_units=selected_modules[index - 1 :],
                progress_ratio=(index - 1) / total_modules if total_modules else 0.0,
            )
            raise
        except Exception as exc:  # pragma: no cover - integration logging
            logging.error("%s 执行失败: %s", module_name, exc)
            emit_progress(
                progress_callback,
                "module_error",
                module_name=module_name,
                message=str(exc),
                completed_units=completed_modules,
                pending_units=selected_modules[index:],
                progress_ratio=(index - 1) / total_modules if total_modules else 0.0,
            )
            raise
        completed_modules.append(module_name)
        emit_progress(
            progress_callback,
            "module_complete",
            module_name=module_name,
            completed_units=completed_modules,
            pending_units=selected_modules[index:],
            progress_ratio=index / total_modules if total_modules else 1.0,
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="资产管理周报主入口。")
    parser.add_argument("--debug", action="store_true", default=None, help="启用 debug 运行模式。")
    parser.add_argument(
        "--modules",
        nargs="+",
        choices=CONFIG["modules"],
        help="指定执行模块，默认执行全部模块。",
    )
    parser.add_argument(
        "--stock-markets",
        nargs="+",
        choices=STOCK_MARKET_OPTIONS,
        help="指定股票模块覆盖的市场列表。",
    )
    parser.add_argument("--bond-date", help="债券模块单次运行日期，支持 YYYYMMDD 或 YYYY-MM-DD。")
    parser.add_argument("--bond-start-date", help="债券模块补录开始日期，支持 YYYYMMDD 或 YYYY-MM-DD。")
    parser.add_argument("--bond-end-date", help="债券模块补录结束日期，支持 YYYYMMDD 或 YYYY-MM-DD。")
    parser.add_argument("--bond-write-history", action="store_true", default=None, help="债券模块单次运行时在 output 根目录额外输出 bonds_YYYYMMDD.xlsx。")
    parser.add_argument("--bond-skip-snapshot-update", action="store_true", default=None, help="债券模块只生成 Excel，不更新 snapshot。")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    main(
        debug=args.debug,
        modules=args.modules,
        stock_markets=args.stock_markets,
        bond_date=args.bond_date,
        bond_start_date=args.bond_start_date,
        bond_end_date=args.bond_end_date,
        bond_write_history=args.bond_write_history,
        bond_update_snapshot=None if args.bond_skip_snapshot_update is None else (not args.bond_skip_snapshot_update),
    )
