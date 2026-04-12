from __future__ import annotations

import math

import pandas as pd

from src.asset_mgnt_report.metrics.annualization import annualized_return_from_returns
from src.asset_mgnt_report.metrics.returns import compute_daily_returns, relative_change
from src.asset_mgnt_report.metrics.sharpe import sharpe_ratio
from src.asset_mgnt_report.metrics.volatility import annualized_volatility


def test_compute_daily_returns() -> None:
    prices = pd.Series([100, 110, 121], index=pd.date_range("2026-01-01", periods=3))
    returns = compute_daily_returns(prices)
    assert len(returns) == 2
    assert math.isclose(returns.iloc[0], 0.1)
    assert math.isclose(returns.iloc[1], 0.1)


def test_annualized_return_from_returns() -> None:
    returns = pd.Series([0.01] * 252)
    result = annualized_return_from_returns(returns)
    assert result > 0.0


def test_annualized_volatility() -> None:
    returns = pd.Series([0.01, -0.01] * 30)
    result = annualized_volatility(returns)
    assert result > 0.0


def test_sharpe_ratio() -> None:
    result = sharpe_ratio(0.12, 0.2, 0.03)
    assert math.isclose(result, 0.45)


def test_relative_change() -> None:
    prices = pd.Series([100, 110, 120, 130])
    result = relative_change(prices, 2)
    assert result > 0
