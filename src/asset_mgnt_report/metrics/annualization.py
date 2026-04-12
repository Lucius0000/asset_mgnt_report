from __future__ import annotations

import math
import pandas as pd


def annualized_return_from_returns(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    clean = pd.to_numeric(daily_returns, errors="coerce").dropna()
    if len(clean) < 2:
        return float("nan")
    compounded = (1.0 + clean).prod()
    years = len(clean) / periods_per_year
    if years <= 0 or compounded <= 0:
        return float("nan")
    return float(compounded ** (1 / years) - 1.0)


def annualized_return_from_prices(price_series: pd.Series, periods_per_year: int = 252) -> float:
    clean = pd.to_numeric(price_series, errors="coerce").dropna()
    if len(clean) < 2:
        return float("nan")
    total_return = clean.iloc[-1] / clean.iloc[0]
    years = (len(clean) - 1) / periods_per_year
    if years <= 0 or total_return <= 0:
        return float("nan")
    return float(total_return ** (1 / years) - 1.0)


def cagr_from_percent_series(percent_series: pd.Series) -> float:
    clean = pd.to_numeric(percent_series, errors="coerce").dropna() / 100.0
    if clean.empty:
        return float("nan")
    compounded = (1.0 + clean).prod()
    periods = len(clean)
    if periods <= 0 or compounded <= 0:
        return float("nan")
    return float(math.pow(compounded, 1 / periods) - 1.0)
