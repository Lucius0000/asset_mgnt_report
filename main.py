"""
直接执行该代码，即可调用其余各个脚本，方便一键执行指标分析。
"""

from __future__ import annotations

import logging

from src.asset_mgnt_report.config.defaults import build_app_config
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
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main(debug: bool | None = None, modules: list[str] | None = None) -> None:
    config = build_app_config(overrides={"debug": CONFIG["debug"] if debug is None else debug})
    selected_modules = modules or CONFIG["modules"]
    for module_name in selected_modules:
        try:
            run_named_pipeline(module_name, debug=config.debug)
        except TypeError:
            run_named_pipeline(module_name)
        except Exception as exc:  # pragma: no cover - integration logging
            logging.error("%s 执行失败: %s", module_name, exc)


if __name__ == "__main__":
    main()
