from __future__ import annotations

import math
import pandas as pd


def annualized_volatility(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    clean = pd.to_numeric(daily_returns, errors="coerce").dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * math.sqrt(periods_per_year))
