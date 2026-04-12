from __future__ import annotations

from importlib import import_module
from pathlib import Path
import runpy
from typing import Callable


MODULE_RUNNERS: dict[str, tuple[str, str | None]] = {
    "cpi": ("cpi", "main"),
    "gdp": ("GDP_new", "main"),
    "interest_rate": ("interest_rate", "main"),
    "carry_trade": ("carry_trade", "main"),
    "stock_index": ("asset_stock_index", "main"),
    "currency": ("currency", "main"),
    "precious_metals": ("precious_metals.py", None),
    "bonds": ("bonds", "main"),
    "crypto": ("crypto_market_report", "main"),
    "gainer": ("Gainer", "main"),
    "overall": ("整体.py", None),
    "secondary_market": ("stock_us_cn_hk/market_report_china_hk_2weeks.py", None),
}


def get_runner(name: str) -> Callable:
    module_name, attr = MODULE_RUNNERS[name]
    if attr is None:
        script_path = Path(module_name)

        def _run_script(**_: object) -> None:
            runpy.run_path(str(script_path), run_name="__main__")

        return _run_script
    module = import_module(module_name)
    return getattr(module, attr)


def run_named_pipeline(name: str, **kwargs: object) -> None:
    runner = get_runner(name)
    runner(**kwargs)
