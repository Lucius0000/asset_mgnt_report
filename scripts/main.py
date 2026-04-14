from __future__ import annotations

import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.services.progress import JobCancelledError, emit_progress, ensure_not_cancelled
from src.asset_mgnt_report.services.runtime import run_named_pipeline

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
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

STOCK_MARKET_OPTIONS = ("CN", "US", "HK")


def _normalize_stock_markets(stock_markets: list[str] | None) -> list[str]:
    selected = stock_markets or CONFIG["stock_markets"]
    normalized = [market.upper() for market in selected if market and market.upper() in STOCK_MARKET_OPTIONS]
    # 保持顺序稳定，避免 UI / CLI 选择顺序影响输出列顺序。
    return [market for market in STOCK_MARKET_OPTIONS if market in normalized]


def main(
    debug: bool | None = None,
    modules: list[str] | None = None,
    stock_markets: list[str] | None = None,
    progress_callback=None,
    cancel_check=None,
) -> None:
    config = build_app_config(overrides={"debug": CONFIG["debug"] if debug is None else debug})
    selected_modules = modules or CONFIG["modules"]
    selected_stock_markets = _normalize_stock_markets(stock_markets)
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


if __name__ == "__main__":
    main()
