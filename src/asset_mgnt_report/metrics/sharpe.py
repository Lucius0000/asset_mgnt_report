from __future__ import annotations

import math


def sharpe_ratio(annualized_return: float, annualized_volatility_value: float, risk_free_rate: float) -> float:
    if any(math.isnan(v) for v in (annualized_return, annualized_volatility_value)):
        return float("nan")
    if annualized_volatility_value == 0:
        return float("nan")
    return (annualized_return - risk_free_rate) / annualized_volatility_value


def adjusted_sharpe_ratio(
    annualized_return: float,
    annualized_volatility_value: float,
    risk_free_rate: float,
    currency_adjustment: float = 0.0,
) -> float:
    if annualized_volatility_value == 0:
        return float("nan")
    return (annualized_return + currency_adjustment - risk_free_rate) / annualized_volatility_value
