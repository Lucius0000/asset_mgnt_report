"""Calculate the change in gold total market capitalization across two weekends."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.asset_mgnt_report.config.inputs import resolve_config_value

ABOVE_GROUND_STOCK_TONS = 216_265  # Modify as needed to reflect above-ground gold stock in tons.
OZT_PER_TON = 32_150.7466

# 顶部配置区（适合 Spyder 直接运行）
# - current_price / previous_price: 浮点数，单位 USD/oz，例如 3240.5
CONFIG = {
    "current_price": None,
    "previous_price": None,
}


def _prompt_price(prompt: str, env_key: str | None = None, configured: float | None = None) -> float:
    resolved = resolve_config_value(explicit=configured, env_key=env_key, caster=float)
    if resolved is not None:
        return resolved
    while True:
        user_input = input(prompt).strip()
        if not user_input:
            print("请输入价格，允许使用数字和逗号，例如 2035.25 或 2,035.25。")
            continue
        cleaned = user_input.replace(",", "")
        try:
            price = float(cleaned)
        except ValueError:
            print("无法解析输入，请输入有效的 LBMA Gold Price PM 数值。")
            continue
        if price < 0:
            print("价格不能为负数，请重新输入。")
            continue
        return price


def _calc_total_market_cap(price_pm: float) -> float:
    return ABOVE_GROUND_STOCK_TONS * OZT_PER_TON * price_pm


def _format_billion_usd(value: float) -> str:
    return f"{value / 1_000_000_000:,.2f} B USD"


def main(
    current_price: float | None = None,
    previous_price: float | None = None,
) -> None:
    print("计算黄金总市值差值：本周末总市值 - 前两周周末总市值\n")
    current_price = _prompt_price(
        "请输入本周末的 LBMA Gold Price PM（USD/oz）：",
        env_key="AMR_GOLD_CURRENT_PRICE",
        configured=current_price if current_price is not None else CONFIG["current_price"],
    )
    previous_price = _prompt_price(
        "请输入前两周周末的 LBMA Gold Price PM（USD/oz）：",
        env_key="AMR_GOLD_PREVIOUS_PRICE",
        configured=previous_price if previous_price is not None else CONFIG["previous_price"],
    )

    current_cap = _calc_total_market_cap(current_price)
    previous_cap = _calc_total_market_cap(previous_price)
    diff = current_cap - previous_cap

    print("\n结果：")
    print(f"本周末总市值：{_format_billion_usd(current_cap)}")
    print(f"前两周周末总市值：{_format_billion_usd(previous_cap)}")
    print(f"差值（本周末 - 前两周）：{_format_billion_usd(diff)}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="计算黄金总市值 Gainer。")
    parser.add_argument("--current-price", type=float, help="本周末的 LBMA Gold Price PM（USD/oz）。")
    parser.add_argument("--previous-price", type=float, help="前两周周末的 LBMA Gold Price PM（USD/oz）。")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    main(
        current_price=args.current_price,
        previous_price=args.previous_price,
    )
