from __future__ import annotations

from pathlib import Path

from scripts.entrypoints import run_overall

CONFIG = {
    "input_path": Path("data") / "seeds" / "整体.xlsx",
    "output_path": Path("output") / "整体_processed.xlsx",
    "log_path": Path("output") / "raw_data" / "整体_calculation_steps.txt",
}


def main() -> None:
    run_overall.CONFIG.update(CONFIG)
    run_overall.main()


if __name__ == "__main__":
    main()
