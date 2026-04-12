from __future__ import annotations

from scripts.entrypoints import run_main as run_main_entry

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

def main(debug: bool | None = None, modules: list[str] | None = None) -> None:
    run_main_entry.CONFIG.update(CONFIG)
    run_main_entry.main(debug=debug, modules=modules)


if __name__ == "__main__":
    main()
