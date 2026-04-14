"""
CPI 分析，输出：
- output/cpi_metrics.xlsx
- output/cpi_trends.png
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import akshare as ak
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.asset_mgnt_report.config.defaults import build_app_config


APP_CONFIG = build_app_config()
OUTPUT_DIR = APP_CONFIG.output_dir
RAW_DATA_DIR = APP_CONFIG.raw_output_dir
SEED_DATA_DIR = APP_CONFIG.seed_data_dir

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

FRED_SERIES = {
    "US_CPI": ("CPIAUCSL", "美国", "CPI", "fred"),
    "US_PCE": ("PCEPILFE", "美国", "核心 PCE", "fred"),
}
CHINA_OFFICIAL_SOURCE = "china_nbs"
CHINA_FALLBACK_SOURCE = "china_akshare_macro_china_cpi"
CHINA_CACHE_SOURCE = "china_cache"
HK_API_SOURCE = "hk_censtatd_api"
HK_LOCAL_SOURCE = "hk_local_seed_fallback"
US_FALLBACK_SOURCE = "akshare_macro"


def _normalize_month_timestamp(value: Any) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        return value.normalize().replace(day=1)
    text = str(value).strip()
    if not text:
        return pd.NaT
    if "年" in text and "月" in text:
        year = text.split("年")[0]
        month = text.split("年")[1].split("月")[0].zfill(2)
        return pd.Timestamp(f"{year}-{month}-01")
    if len(text) == 6 and text.isdigit():
        return pd.Timestamp(f"{text[:4]}-{text[4:6]}-01")
    ts = pd.to_datetime(text, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    return ts.normalize().replace(day=1)


def _clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"\[.*?\]", "", regex=True).str.replace("φ", "").str.replace("+", ""),
        errors="coerce",
    )


def _empty_standard_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["日期", "指数", "YoY", "MoM", "数据源"])


def _standardize_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = df.copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
    out["指数"] = pd.to_numeric(out["指数"], errors="coerce")
    out["YoY"] = pd.to_numeric(out["YoY"], errors="coerce")
    out["MoM"] = pd.to_numeric(out["MoM"], errors="coerce")
    out["数据源"] = source
    out = out.dropna(subset=["日期"]).sort_values("日期").drop_duplicates(subset=["日期"], keep="last")
    return out.reset_index(drop=True)


def _build_metrics_frame_from_index(index_df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = index_df[["日期", "指数"]].copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
    out["指数"] = pd.to_numeric(out["指数"], errors="coerce")
    out = out.dropna(subset=["日期", "指数"]).sort_values("日期")
    out["MoM"] = out["指数"].pct_change(1) * 100
    out["YoY"] = out["指数"].pct_change(12) * 100
    out["数据源"] = source
    return out.reset_index(drop=True)


def _save_raw_frame(name: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    df.to_excel(RAW_DATA_DIR / name, index=False)


def _compute_index_cagr(series_df: pd.DataFrame, years: int = 10) -> tuple[float | None, str | None]:
    valid = series_df.dropna(subset=["日期", "指数"]).sort_values("日期")
    if len(valid) < 2:
        return None, None
    latest = valid.iloc[-1]
    start_target = latest["日期"] - pd.DateOffset(years=years)
    candidates = valid[valid["日期"] >= start_target]
    start_row = candidates.iloc[0] if not candidates.empty else valid.iloc[0]
    if start_row["日期"] >= latest["日期"] or start_row["指数"] <= 0 or latest["指数"] <= 0:
        return None, None
    year_span = (latest["日期"] - start_row["日期"]).days / 365.25
    if year_span <= 0:
        return None, None
    cagr = ((latest["指数"] / start_row["指数"]) ** (1 / year_span) - 1) * 100
    date_range = f"{start_row['日期'].strftime('%Y-%m')} to {latest['日期'].strftime('%Y-%m')}"
    return float(cagr), date_range


def _format_metric_date(dt: Any) -> str:
    if pd.isna(dt):
        return "-"
    return pd.to_datetime(dt).strftime("%Y-%m")


def _fetch_fred_series(series_id: str) -> pd.DataFrame:
    if not APP_CONFIG.fred_api_key:
        raise RuntimeError("缺少 FRED_API_KEY，无法请求 FRED 官方 CPI/PCE 数据。")
    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": APP_CONFIG.fred_api_key,
            "file_type": "json",
            "sort_order": "asc",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    observations = payload.get("observations", [])
    frame = pd.DataFrame(observations)
    if frame.empty:
        raise ValueError(f"FRED 序列 {series_id} 返回空数据。")
    frame["日期"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["指数"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame[["日期", "指数"]].dropna(subset=["日期", "指数"])


def _fetch_us_series_with_fred(series_id: str, source_name: str) -> pd.DataFrame:
    fred_df = _fetch_fred_series(series_id)
    standardized = _build_metrics_frame_from_index(fred_df, source_name)
    if standardized.empty:
        raise ValueError(f"FRED 序列 {series_id} 标准化后为空。")
    return standardized


def _fallback_us_cpi() -> pd.DataFrame:
    monthly = ak.macro_usa_cpi_monthly()[["日期", "今值"]].copy()
    monthly["日期"] = pd.to_datetime(monthly["日期"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    monthly["MoM"] = pd.to_numeric(monthly["今值"], errors="coerce")
    yearly = ak.macro_usa_cpi_yoy()[["时间", "现值"]].copy()
    yearly["日期"] = pd.to_datetime(yearly["时间"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    yearly["YoY"] = pd.to_numeric(yearly["现值"], errors="coerce")
    merged = monthly[["日期", "MoM"]].merge(yearly[["日期", "YoY"]], on="日期", how="outer").sort_values("日期")
    merged["指数"] = np.nan
    merged["数据源"] = US_FALLBACK_SOURCE
    return merged[["日期", "指数", "YoY", "MoM", "数据源"]].dropna(subset=["日期"]).reset_index(drop=True)


def _fallback_us_pce() -> pd.DataFrame:
    pce = ak.macro_usa_core_pce_price()[["日期", "今值"]].copy()
    pce["日期"] = pd.to_datetime(pce["日期"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    pce["YoY"] = pd.to_numeric(pce["今值"], errors="coerce")
    pce["MoM"] = np.nan
    pce["指数"] = np.nan
    pce["数据源"] = US_FALLBACK_SOURCE
    return pce[["日期", "指数", "YoY", "MoM", "数据源"]].dropna(subset=["日期"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def _discover_nbs_indicator_codes() -> dict[str, str]:
    from akshare.economic import macro_china_nbs

    codes: dict[str, str] = {}
    dbcode = "hgyd"
    queue: list[tuple[str, int]] = [("zb", 0)]
    visited: set[str] = set()
    while queue:
        node_id, depth = queue.pop(0)
        if node_id in visited or depth > 6:
            continue
        visited.add(node_id)
        nodes = macro_china_nbs._get_nbs_tree(node_id, dbcode)  # type: ignore[attr-defined]
        for node in nodes:
            name = str(node.get("name") or node.get("cname") or "")
            child_id = str(node.get("id") or "")
            if not child_id:
                continue
            lowered = name.replace(" ", "")
            if "居民消费价格指数" in lowered and "上年同月=100" in lowered and "yoy" not in codes:
                codes["yoy"] = child_id
            if "居民消费价格指数" in lowered and "上月=100" in lowered and "mom" not in codes:
                codes["mom"] = child_id
            is_parent = str(node.get("isParent", "")).lower() in {"true", "1"} or node.get("isParent") is True
            if is_parent:
                queue.append((child_id, depth + 1))
        if "yoy" in codes and "mom" in codes:
            break
    return codes


def _query_nbs_indicator(indicator_id: str, period: str = "LAST180") -> pd.DataFrame:
    response = requests.get(
        "https://data.stats.gov.cn/easyquery.htm",
        params={
            "m": "QueryData",
            "dbcode": "hgyd",
            "rowcode": "zb",
            "colcode": "sj",
            "wds": "[]",
            "dfwds": json.dumps(
                [
                    {"wdcode": "zb", "valuecode": indicator_id},
                    {"wdcode": "sj", "valuecode": period},
                ],
                ensure_ascii=False,
            ),
            "k1": str(int(datetime.now().timestamp() * 1000)),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    datanodes = payload["returndata"]["datanodes"]
    wdnodes = payload["returndata"]["wdnodes"]
    period_nodes = next(node["nodes"] for node in wdnodes if node["wdcode"] == "sj")
    period_map = {node["code"]: node["cname"] for node in period_nodes}
    records = []
    for item in datanodes:
        data_info = item.get("data", {})
        if not data_info.get("hasdata"):
            continue
        code = item["wds"][1]["valuecode"]
        records.append({"日期": _normalize_month_timestamp(period_map.get(code, code)), "值": data_info.get("data")})
    frame = pd.DataFrame(records)
    frame["值"] = pd.to_numeric(frame["值"], errors="coerce")
    return frame.dropna(subset=["日期"]).sort_values("日期")


def _fetch_china_cpi_from_nbs_official() -> pd.DataFrame:
    codes = _discover_nbs_indicator_codes()
    if "yoy" not in codes or "mom" not in codes:
        raise RuntimeError("未能从国家统计局目录树中解析中国 CPI 所需指标编码。")
    yoy_df = _query_nbs_indicator(codes["yoy"]).rename(columns={"值": "YoYIndex"})
    mom_df = _query_nbs_indicator(codes["mom"]).rename(columns={"值": "MoMIndex"})
    merged = yoy_df.merge(mom_df, on="日期", how="outer").sort_values("日期")
    merged["YoY"] = merged["YoYIndex"] - 100
    merged["MoM"] = merged["MoMIndex"] - 100
    merged["指数"] = np.nan
    merged["数据源"] = CHINA_OFFICIAL_SOURCE
    standardized = merged[["日期", "指数", "YoY", "MoM", "数据源"]].dropna(subset=["日期"]).reset_index(drop=True)
    if standardized.empty:
        raise RuntimeError("国家统计局官方链路返回空数据。")
    return standardized


def _fetch_china_cpi_from_akshare() -> pd.DataFrame:
    frame = ak.macro_china_cpi().copy()
    standardized = frame.rename(
        columns={
            "月份": "日期",
            "全国-当月": "指数",
            "全国-同比增长": "YoY",
            "全国-环比增长": "MoM",
        }
    )
    standardized["日期"] = standardized["日期"].apply(_normalize_month_timestamp)
    standardized["指数"] = pd.to_numeric(standardized["指数"], errors="coerce")
    standardized["YoY"] = pd.to_numeric(standardized["YoY"], errors="coerce")
    standardized["MoM"] = pd.to_numeric(standardized["MoM"], errors="coerce")
    standardized["数据源"] = CHINA_FALLBACK_SOURCE
    standardized = standardized[["日期", "指数", "YoY", "MoM", "数据源"]]
    return standardized.dropna(subset=["日期"]).sort_values("日期").reset_index(drop=True)


def _load_cached_cpi_frame(cache_path: Path, source_name: str) -> pd.DataFrame:
    if not cache_path.exists():
        raise FileNotFoundError(f"未找到本地缓存：{cache_path}")
    frame = pd.read_excel(cache_path)
    standardized = _standardize_frame(frame, source_name)
    if standardized.empty:
        raise ValueError(f"本地缓存为空：{cache_path}")
    return standardized


def load_hk_composite_cpi(file_path: Path) -> pd.DataFrame:
    df = pd.read_excel(file_path, sheet_name=0, header=None, skiprows=5)
    df = df.rename(columns={0: "年", 1: "月", 2: "指数", 3: "YoY", 4: "MoM"})
    df["年"] = df["年"].ffill()
    df = df[df["月"].notna() & df["YoY"].notna()]
    df["月"] = df["月"].astype(int).astype(str).str.zfill(2)
    df["年"] = df["年"].astype(int).astype(str)
    df["日期"] = pd.to_datetime(df["年"] + df["月"], format="%Y%m")
    df["指数"] = _clean_numeric(df["指数"])
    df["YoY"] = _clean_numeric(df["YoY"])
    df["MoM"] = _clean_numeric(df["MoM"])
    df["数据源"] = HK_LOCAL_SOURCE
    return df[["日期", "指数", "YoY", "MoM", "数据源"]].dropna(subset=["日期"]).reset_index(drop=True)


def _fetch_hk_cpi_from_api(period_start: str | None = None) -> pd.DataFrame:
    if period_start is None:
        period_start = (pd.Timestamp.today().normalize() - pd.DateOffset(years=12)).strftime("%Y%m")
    parameters = {
        "cv": {},
        "sv": {"CC_CM_1920": ["Raw_1dp_idx_n", "MoM_1dp_%_s", "YoY_1dp_%_s"]},
        "period": {"start": period_start},
        "id": "510-60001",
        "lang": "en",
    }
    response = requests.post(
        "https://www.censtatd.gov.hk/api/post.php",
        data={"query": json.dumps(parameters)},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    status = payload.get("header", {}).get("status", {})
    if status.get("code") != 0:
        raise RuntimeError(f"香港统计处 API 失败: {status}")
    records = []
    for item in payload.get("dataSet", []):
        if item.get("freq") != "M":
            continue
        sv_desc = str(item.get("svDesc", "")).strip()
        records.append(
            {
                "日期": _normalize_month_timestamp(item.get("period")),
                "字段": sv_desc,
                "值": item.get("figure"),
            }
        )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("香港统计处 API 未返回月度 Composite CPI 数据。")
    pivot = frame.pivot_table(index="日期", columns="字段", values="值", aggfunc="last").reset_index()
    standardized = pivot.rename(
        columns={
            "Index": "指数",
            "Month-to-month % change": "MoM",
            "Year-on-year % change": "YoY",
        }
    )
    standardized["数据源"] = HK_API_SOURCE
    return _standardize_frame(standardized[["日期", "指数", "YoY", "MoM", "数据源"]], HK_API_SOURCE)


def _load_hk_local_fallback() -> pd.DataFrame:
    local_candidates = sorted(SEED_DATA_DIR.glob("Table 510*.xlsx"))
    if not local_candidates:
        raise FileNotFoundError("未找到匹配的 Table 510*.xlsx 文件")
    latest_file = max(local_candidates, key=lambda path: path.stat().st_mtime)
    logger.warning("香港 CPI API 失败，回退到本地种子表格: %s", latest_file)
    return load_hk_composite_cpi(latest_file)


def get_cpi_data(time_range: int = 200) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}

    for key, (series_id, region, indicator, source_name) in FRED_SERIES.items():
        try:
            data[key] = _fetch_us_series_with_fred(series_id, source_name).tail(time_range).reset_index(drop=True)
        except Exception as exc:
            logger.warning("%s %s 官方 FRED 失败，回退到 AkShare：%s", region, indicator, exc)
            fallback = _fallback_us_cpi if key == "US_CPI" else _fallback_us_pce
            data[key] = fallback().tail(time_range).reset_index(drop=True)

    try:
        data["CN_CPI"] = _fetch_china_cpi_from_nbs_official().tail(time_range).reset_index(drop=True)
    except Exception as exc:
        logger.warning("中国 CPI 官方链路失败，回退到 AkShare macro_china_cpi(): %s", exc)
        try:
            data["CN_CPI"] = _fetch_china_cpi_from_akshare().tail(time_range).reset_index(drop=True)
        except Exception as fallback_exc:
            logger.warning("中国 CPI AkShare 回退失败，尝试读取本地缓存：%s", fallback_exc)
            cache_path = RAW_DATA_DIR / "cpi_cn_cpi.xlsx"
            data["CN_CPI"] = _load_cached_cpi_frame(cache_path, CHINA_CACHE_SOURCE).tail(time_range).reset_index(drop=True)

    try:
        data["HK_CPI"] = _fetch_hk_cpi_from_api().tail(time_range).reset_index(drop=True)
    except Exception as exc:
        logger.warning("香港 CPI 官方 API 失败，回退到本地种子表格：%s", exc)
        data["HK_CPI"] = _load_hk_local_fallback().tail(time_range).reset_index(drop=True)

    return data


def calculate_cpi_metrics(cpi_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    result_rows: list[dict[str, Any]] = []
    mapping = {
        "US_CPI": ("美国", "CPI"),
        "US_PCE": ("美国", "核心 PCE"),
        "CN_CPI": ("中国", "CPI"),
        "HK_CPI": ("香港", "CPI"),
    }
    for key, (region, indicator) in mapping.items():
        frame = cpi_data.get(key)
        if frame is None or frame.empty:
            continue
        valid = frame.sort_values("日期").reset_index(drop=True)
        latest_mom = valid.dropna(subset=["MoM"]).iloc[-1] if valid["MoM"].notna().any() else None
        latest_yoy = valid.dropna(subset=["YoY"]).iloc[-1] if valid["YoY"].notna().any() else None
        cagr_10y, date_range = _compute_index_cagr(valid)
        result_rows.append(
            {
                "region": region,
                "indicator": indicator,
                "mom_value": None if latest_mom is None else latest_mom["MoM"],
                "mom_date": None if latest_mom is None else latest_mom["日期"],
                "yoy_value": None if latest_yoy is None else latest_yoy["YoY"],
                "yoy_date": None if latest_yoy is None else latest_yoy["日期"],
                "cagr_10y": cagr_10y,
                "date_range": date_range,
                "data_source": valid["数据源"].dropna().iloc[-1] if valid["数据源"].notna().any() else "",
            }
        )
    return pd.DataFrame(result_rows)


def plot_cpi_trends(cpi_data: dict[str, pd.DataFrame]) -> None:
    latest_dates = [
        pd.to_datetime(frame["日期"], errors="coerce").dropna().max()
        for frame in cpi_data.values()
        if frame is not None and not frame.empty
    ]
    if not latest_dates:
        return
    window_end = max(latest_dates)
    window_start = window_end - pd.DateOffset(years=10)

    plt.rcParams["font.family"] = "SimHei"
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(12, 6))

    plot_specs = [
        ("US_CPI", "美国 CPI YoY"),
        ("US_PCE", "美国核心 PCE YoY"),
        ("CN_CPI", "中国 CPI YoY"),
        ("HK_CPI", "香港 CPI YoY"),
    ]
    for key, label in plot_specs:
        frame = cpi_data.get(key)
        if frame is None or frame.empty:
            continue
        series = frame.dropna(subset=["日期", "YoY"]).copy()
        series["日期"] = pd.to_datetime(series["日期"], errors="coerce")
        series = series[(series["日期"] >= window_start) & (series["日期"] <= window_end)]
        if series.empty:
            continue
        ax.plot(series["日期"], series["YoY"], label=label, linestyle="--")

    ax.set_title("CPI / PCE 同比（最近 10 年）")
    ax.set_xlabel("时间")
    ax.set_ylabel("%")
    ax.legend()
    ax.grid(True)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "cpi_trends.png")
    plt.close(fig)


def generate_report(debug: bool = False) -> pd.DataFrame:
    print("=" * 50)
    print("宏观经济指标统计")
    print("=" * 50)
    print(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n1. CPI分析")
    print("-" * 30)

    cpi_data = get_cpi_data(time_range=240)
    if debug:
        for name, frame in cpi_data.items():
            print(f"\n[{name}]")
            print(frame.tail(5))

    for name, frame in cpi_data.items():
        _save_raw_frame(f"cpi_{name.lower()}.xlsx", frame)

    cpi_metrics = calculate_cpi_metrics(cpi_data)
    print(cpi_metrics)

    formatted_df = cpi_metrics.apply(
        lambda row: pd.Series(
            {
                "区域": row["region"],
                "指标": row["indicator"],
                "MoM (%)": "-" if pd.isna(row["mom_value"]) else round(float(row["mom_value"]), 2),
                "MoM 日期": _format_metric_date(row["mom_date"]),
                "YoY (%)": "-" if pd.isna(row["yoy_value"]) else round(float(row["yoy_value"]), 2),
                "YoY 日期": _format_metric_date(row["yoy_date"]),
                "年化增长10年均值（%）": "-" if pd.isna(row["cagr_10y"]) else round(float(row["cagr_10y"]), 2),
                "年化增长10年均值日期": row["date_range"] or "-",
                "数据源": row["data_source"],
            }
        ),
        axis=1,
    )
    formatted_df.to_excel(OUTPUT_DIR / "cpi_metrics.xlsx", index=False)
    plot_cpi_trends(cpi_data)
    return formatted_df


def main(debug: bool = False) -> None:
    try:
        generate_report(debug=debug)
    except Exception as exc:
        logger.error("生成 CPI 报告时出错: %s", exc)
        raise


if __name__ == "__main__":
    main()
