from __future__ import annotations

from scripts.entrypoints import run_gainer

CONFIG = {
    "current_date": None,
    "previous_date": None,
    "current_gold_price": None,
    "previous_gold_price": None,
}


def main() -> None:
    run_gainer.CONFIG.update(CONFIG)
    run_gainer.main()


if __name__ == "__main__":
    main()
