from __future__ import annotations

from importlib import import_module
import runpy
from typing import Callable


MODULE_RUNNERS: dict[str, tuple[str, str | None]] = {
    "cpi": ("scripts.pipelines.cpi_report", "main"),
    "gdp": ("scripts.pipelines.gdp_report", "main"),
    "interest_rate": ("scripts.pipelines.interest_rate_report", "main"),
    "carry_trade": ("scripts.pipelines.carry_trade_report", "main"),
    "stock_index": ("scripts.pipelines.stock_index_report", "main"),
    "currency": ("scripts.pipelines.fx_report", "main"),
    "precious_metals": ("scripts.pipelines.precious_metals_report", None),
    "bonds": ("scripts.pipelines.bond_report", "main"),
    "crypto": ("scripts.pipelines.crypto_report", "main"),
    "gainer": ("scripts.gainer", "main"),
    "overall": ("scripts.overall", "main"),
    "secondary_market": ("scripts.pipelines.secondary_market_report", "main"),
}


def get_runner(name: str) -> Callable:
    module_name, attr = MODULE_RUNNERS[name]
    if attr is None:
        def _run_module(**_: object) -> None:
            runpy.run_module(module_name, run_name="__main__")

        return _run_module
    module = import_module(module_name)
    return getattr(module, attr)


def run_named_pipeline(name: str, **kwargs: object) -> None:
    runner = get_runner(name)
    runner(**kwargs)
