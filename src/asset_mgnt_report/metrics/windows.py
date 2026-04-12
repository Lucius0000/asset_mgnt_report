from __future__ import annotations

from datetime import timedelta
import pandas as pd


def slice_by_days(df: pd.DataFrame, date_col: str, days: int, end_date: pd.Timestamp | None = None) -> pd.DataFrame:
    end = end_date or pd.to_datetime(df[date_col]).max()
    start = end - pd.Timedelta(days=days)
    date_series = pd.to_datetime(df[date_col])
    return df.loc[date_series >= start]


def nearest_value_in_window(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    target_date: pd.Timestamp,
    tolerance_days: int,
) -> float | None:
    dates = pd.to_datetime(df[date_col])
    deltas = (dates - target_date).abs()
    within = df.loc[deltas <= timedelta(days=tolerance_days)]
    if within.empty:
        return None
    idx = deltas.loc[within.index].idxmin()
    value = within.loc[idx, value_col]
    if pd.isna(value):
        return None
    return float(value)
