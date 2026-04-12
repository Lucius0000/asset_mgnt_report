from __future__ import annotations

import numpy as np
import pandas as pd


def compute_daily_returns(price_series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(price_series, errors="coerce").dropna().sort_index()
    return clean.pct_change().dropna()


def relative_change(price_series: pd.Series, periods: int) -> float:
    clean = pd.to_numeric(price_series, errors="coerce").dropna()
    if len(clean) <= periods:
        return float("nan")
    base = clean.iloc[-periods - 1]
    current = clean.iloc[-1]
    if pd.isna(base) or base == 0:
        return float("nan")
    return float(current / base - 1.0)


def trailing_percentile(price_series: pd.Series, window: int = 252) -> float:
    clean = pd.to_numeric(price_series, errors="coerce").dropna().iloc[-window:]
    if len(clean) < 2:
        return float("nan")
    return float(clean.rank(pct=True).iloc[-1])


def product_return(percent_series: pd.Series) -> float:
    clean = pd.to_numeric(percent_series, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    return float(np.prod(1 + clean / 100.0) - 1.0)
