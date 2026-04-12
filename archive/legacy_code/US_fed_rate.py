import os
import requests
import pandas as pd

def get_effr_from_fred(start=None, end=None, series_id="DFF"):
    """
    获取 EFFR:
      - 日频：series_id="DFF"
      - 月均：series_id="FEDFUNDS"
    参数:
      start/end: 'YYYY-MM-DD' 字符串或 None
    返回:
      pandas.DataFrame，包含日期与数值
    """
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("请先在环境变量中设置 FRED_API_KEY")

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        # optional filters:
        "observation_start": start or "",
        "observation_end": end or "",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()["observations"]

    df = pd.DataFrame(data)[["date", "value"]]
    # 转成数值；FRED 缺失用 "."
    df["value"] = pd.to_numeric(df["value"].replace(".", pd.NA), errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna().set_index("date").sort_index()
    df.rename(columns={"value": series_id}, inplace=True)
    return df

if __name__ == "__main__":
    # 示例：取 2020-01-01 至今的“每日 EFFR”
    effr_daily = get_effr_from_fred(start="2020-01-01", series_id="DFF")
    print(effr_daily.tail())

    # 如果要“月均 EFFR”
    effr_monthly = get_effr_from_fred(start="2020-01-01", series_id="FEDFUNDS")
    print(effr_monthly.tail())
