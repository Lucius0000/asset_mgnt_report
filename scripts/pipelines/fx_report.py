'''
货币汇率分析
输出汇率表：fx_metrics.xlsx
'''

import pandas as pd
import numpy as np
import os
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import akshare as ak
import yfinance as yf

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 汇率代号映射
SYMBOLS = {
    "USD_CNH": "USDCNH",
    "USD_HKD": "USDHKD",
}
OUTPUT_NAMES = {code: name for name, code in SYMBOLS.items()}
YAHOO_SYMBOLS = {
    "USDCNH": "CNH=X",
    "USDHKD": "HKD=X",
}

# 保存路径
RAW_DATA_DIR = "output/raw_data"
os.makedirs(RAW_DATA_DIR, exist_ok=True)


@contextmanager
def _without_proxy_env():
    proxy_keys = [
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ]
    snapshot = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _looks_like_proxy_failure(exc: Exception) -> bool:
    message = str(exc)
    keywords = [
        "ProxyError",
        "Unable to connect to proxy",
        "Remote end closed connection without response",
        "Cannot connect to proxy",
    ]
    return any(keyword in message for keyword in keywords)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _current_proxy() -> str | None:
    for key in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def _mark_source(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df.attrs["data_source"] = source
    return df


def _has_reference_point(df: pd.DataFrame, target_date: pd.Timestamp, tolerance_days: int = 10) -> bool:
    if df.empty:
        return False
    window = df[
        (df["日期"] >= target_date - pd.Timedelta(days=tolerance_days))
        & (df["日期"] <= target_date + pd.Timedelta(days=tolerance_days))
    ]
    return not window.empty


def _has_metric_history(df: pd.DataFrame, *, tolerance_days: int = 10) -> bool:
    if df is None or df.empty:
        return False
    cleaned = _clean_rate_df(df)
    if cleaned.empty:
        return False
    latest = cleaned["日期"].max()
    return _has_reference_point(cleaned, latest - pd.DateOffset(months=1), tolerance_days=tolerance_days) and _has_reference_point(
        cleaned, latest - pd.DateOffset(years=1), tolerance_days=tolerance_days
    )


def _source_loader(source_name: str):
    mapping = {
        "forex_hist_em": get_fx_data,
        "yfinance": _get_fx_data_yfinance,
        "currency_boc_safe": _get_fx_data_boc_safe,
        "currency_boc_sina": _get_fx_data_boc_sina,
        "local_cache": _load_cached_fx_data,
    }
    return mapping[source_name]


def _harmonize_pair_sources(fx_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    usd_cnh = fx_data["USD_CNH"]
    usd_hkd = fx_data["USD_HKD"]
    usd_cnh_source = usd_cnh.attrs.get("data_source", "unknown")
    usd_hkd_source = usd_hkd.attrs.get("data_source", "unknown")

    if usd_cnh_source == usd_hkd_source:
        return fx_data

    for source_name in ("currency_boc_safe", "yfinance", "currency_boc_sina", "local_cache"):
        loader = _source_loader(source_name)
        candidate_usd_cnh = loader("USDCNH")
        candidate_usd_hkd = loader("USDHKD")
        if _has_metric_history(candidate_usd_cnh) and _has_metric_history(candidate_usd_hkd):
            logging.info(
                "检测到 USD_CNH 与 USD_HKD 数据源不一致，已统一切换到 %s 以保证交叉汇率口径一致。",
                source_name,
            )
            return {
                "USD_CNH": candidate_usd_cnh,
                "USD_HKD": candidate_usd_hkd,
            }

    logging.warning(
        "USD_CNH 与 USD_HKD 数据源不一致，且未找到可用的统一回退源；继续保留当前结果。"
    )
    return fx_data


def get_fx_data(symbol_code):
    try:
        df = ak.forex_hist_em(symbol=symbol_code)
    except Exception as e:
        if _looks_like_proxy_failure(e) and _env_bool("AMR_FX_RETRY_WITHOUT_PROXY", True):
            logging.warning(f"拉取 {symbol_code} 历史数据遇到代理错误，尝试直连重试: {e}")
            try:
                with _without_proxy_env():
                    df = ak.forex_hist_em(symbol=symbol_code)
            except Exception as retry_exc:
                logging.error(f"拉取 {symbol_code} 历史数据失败（直连重试后仍失败）: {retry_exc}")
                return _get_fx_data_yfinance(symbol_code)
        else:
            logging.error(f"拉取 {symbol_code} 历史数据失败: {e}")
            return _get_fx_data_yfinance(symbol_code)

    required_columns = {'日期', '最新价'}
    if df is None or df.empty or not required_columns.issubset(df.columns):
        logging.warning(f"{symbol_code} 未返回可用汇率数据。")
        return _get_fx_data_yfinance(symbol_code)

    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    df = df[['日期', '最新价']].rename(columns={'最新价': '汇率'}).dropna()
    if df.empty:
        logging.warning(f"{symbol_code} 历史数据在清洗后为空。")
        return _get_fx_data_yfinance(symbol_code)
    return _mark_source(df, "forex_hist_em")


def _get_fx_data_yfinance(symbol_code):
    ticker = YAHOO_SYMBOLS.get(symbol_code)
    if not ticker:
        return _get_fx_data_official(symbol_code)
    try:
        proxy = _current_proxy()
        df = yf.download(
            ticker,
            period="10y",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
            proxy=proxy,
        )
    except Exception as exc:
        logging.error(f"拉取 {symbol_code} 的 Yahoo Finance 备用数据失败: {exc}")
        return _get_fx_data_official(symbol_code)
    if df is None or df.empty:
        logging.warning(f"{symbol_code} 的 Yahoo Finance 备用数据为空。")
        return _get_fx_data_official(symbol_code)
    close_series = df["Close"]
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:, 0]
    cleaned = (
        close_series.rename("汇率")
        .dropna()
        .reset_index()
        .rename(columns={"Date": "日期"})
    )
    if "日期" not in cleaned.columns:
        cleaned = cleaned.rename(columns={cleaned.columns[0]: "日期"})
    cleaned["日期"] = pd.to_datetime(cleaned["日期"], errors="coerce")
    cleaned = cleaned[["日期", "汇率"]].dropna()
    if cleaned.empty:
        logging.warning(f"{symbol_code} 的 Yahoo Finance 备用数据在清洗后为空。")
        return _get_fx_data_official(symbol_code)
    if not _has_metric_history(cleaned):
        logging.warning(f"{symbol_code} 的 Yahoo Finance 备用数据历史长度不足，继续尝试官方降级源。")
        return _get_fx_data_official(symbol_code)
    logging.info(f"{symbol_code} 已切换到 Yahoo Finance 备用数据源。")
    return _mark_source(cleaned, "yfinance")


def _get_fx_data_official(symbol_code):
    safe_df = _get_fx_data_boc_safe(symbol_code)
    if not safe_df.empty:
        return safe_df
    sina_df = _get_fx_data_boc_sina(symbol_code)
    if not sina_df.empty:
        return sina_df
    return _load_cached_fx_data(symbol_code)


def _clean_rate_df(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned["日期"] = pd.to_datetime(cleaned["日期"], errors="coerce")
    cleaned["汇率"] = pd.to_numeric(cleaned["汇率"], errors="coerce")
    return cleaned[["日期", "汇率"]].dropna()


def _get_fx_data_boc_safe(symbol_code):
    try:
        df = ak.currency_boc_safe()
    except Exception as exc:
        logging.error(f"拉取 {symbol_code} 的 currency_boc_safe 数据失败: {exc}")
        return pd.DataFrame(columns=["日期", "汇率"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["日期", "汇率"])
    if symbol_code == "USDCNH" and "美元" in df.columns:
        cleaned = _clean_rate_df(df[["日期", "美元"]].rename(columns={"美元": "汇率"}))
        cleaned["汇率"] = cleaned["汇率"] / 100.0
        if not cleaned.empty:
            logging.info(f"{symbol_code} 已切换到官方降级源 currency_boc_safe。")
            return _mark_source(cleaned, "currency_boc_safe")
    if symbol_code == "USDHKD" and {"美元", "港元"}.issubset(df.columns):
        merged = _clean_rate_df(df[["日期", "美元"]].rename(columns={"美元": "汇率"})).rename(columns={"汇率": "美元"})
        hkd = _clean_rate_df(df[["日期", "港元"]].rename(columns={"港元": "汇率"})).rename(columns={"汇率": "港元"})
        merged = pd.merge(merged, hkd, on="日期", how="inner")
        if not merged.empty:
            result = merged.assign(汇率=merged["美元"] / merged["港元"])[["日期", "汇率"]]
            logging.info(f"{symbol_code} 已切换到官方降级源 currency_boc_safe。")
            return _mark_source(result, "currency_boc_safe")
    return pd.DataFrame(columns=["日期", "汇率"])


def _pick_boc_sina_value_column(df: pd.DataFrame) -> str | None:
    for column in ("央行中间价", "中行钞卖价/汇卖价", "中行汇买价"):
        if column in df.columns:
            return column
    return None


def _load_boc_sina_series(symbol_name: str) -> pd.DataFrame:
    start_date = (datetime.now() - pd.DateOffset(years=5)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")
    df = ak.currency_boc_sina(symbol=symbol_name, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame(columns=["日期", "汇率"])
    value_column = _pick_boc_sina_value_column(df)
    if value_column is None:
        return pd.DataFrame(columns=["日期", "汇率"])
    return _clean_rate_df(df[["日期", value_column]].rename(columns={value_column: "汇率"}))


def _get_fx_data_boc_sina(symbol_code):
    try:
        if symbol_code == "USDCNH":
            usd = _load_boc_sina_series("美元")
            if not usd.empty:
                usd["汇率"] = usd["汇率"] / 100.0
                logging.info(f"{symbol_code} 已切换到官方降级源 currency_boc_sina。")
                return _mark_source(usd, "currency_boc_sina")
        if symbol_code == "USDHKD":
            usd = _load_boc_sina_series("美元").rename(columns={"汇率": "美元"})
            hkd = _load_boc_sina_series("港币").rename(columns={"汇率": "港元"})
            merged = pd.merge(usd, hkd, on="日期", how="inner")
            if not merged.empty:
                result = merged.assign(汇率=merged["美元"] / merged["港元"])[["日期", "汇率"]]
                logging.info(f"{symbol_code} 已切换到官方降级源 currency_boc_sina。")
                return _mark_source(result, "currency_boc_sina")
    except Exception as exc:
        logging.error(f"拉取 {symbol_code} 的 currency_boc_sina 数据失败: {exc}")
    return pd.DataFrame(columns=["日期", "汇率"])


def _load_cached_fx_data(symbol_code):
    output_name = OUTPUT_NAMES.get(symbol_code, symbol_code)
    cache_path = Path(RAW_DATA_DIR) / f"{output_name}.xlsx"
    if not cache_path.exists():
        logging.warning(f"{symbol_code} 未找到可复用的本地缓存数据。")
        return pd.DataFrame(columns=['日期', '汇率'])
    try:
        cached = pd.read_excel(cache_path)
    except Exception as exc:
        logging.error(f"读取 {symbol_code} 本地缓存失败: {exc}")
        return pd.DataFrame(columns=['日期', '汇率'])
    required_columns = {'日期', '汇率'}
    if cached.empty or not required_columns.issubset(cached.columns):
        logging.warning(f"{symbol_code} 的本地缓存为空或字段不完整。")
        return pd.DataFrame(columns=['日期', '汇率'])
    cached['日期'] = pd.to_datetime(cached['日期'], errors='coerce')
    cached = cached[['日期', '汇率']].dropna()
    if cached.empty:
        logging.warning(f"{symbol_code} 的本地缓存清洗后为空。")
        return pd.DataFrame(columns=['日期', '汇率'])
    logging.info(f"{symbol_code} 已切换到本地缓存数据源: {cache_path}")
    return _mark_source(cached, "local_cache")

def compute_cross_rate(base_df, quote_df):
    if base_df.empty or quote_df.empty:
        logging.warning("交叉汇率计算跳过：基础汇率或报价汇率为空。")
        return pd.DataFrame(columns=['日期', '汇率'])
    df = pd.merge(base_df, quote_df, on='日期', suffixes=('_base', '_quote'))
    df['汇率'] = df['汇率_quote'] / df['汇率_base']
    result = df[['日期', '汇率']]
    base_source = base_df.attrs.get("data_source", "unknown")
    quote_source = quote_df.attrs.get("data_source", "unknown")
    if base_source == quote_source:
        return _mark_source(result, f"derived:{quote_source}")
    return _mark_source(result, f"derived:USD_HKD={quote_source};USD_CNH={base_source}")

def save_raw_data(data_dict):
    for name, df in data_dict.items():
        path = Path(RAW_DATA_DIR) / f"{name}.xlsx"
        if df.empty and path.exists():
            logging.warning(f"{name} 本次为空，保留已有缓存文件: {path}")
            continue
        df.to_excel(path, index=False)

def calculate_metrics(data_dict):
    results = []
    for name, df in data_dict.items():
        try:
            df = df.sort_values('日期', ascending=False).dropna()
            if df.empty:
                logging.warning(f"{name} 无可用数据，跳过指标计算。")
                raise ValueError("empty dataframe")
            now = df.iloc[0]['日期']
            now_val = df.iloc[0]['汇率']

            # MoM
            one_month = now - pd.DateOffset(months=1)
            mom_df = df[(df['日期'] >= one_month - pd.Timedelta(days=10)) & (df['日期'] <= one_month + pd.Timedelta(days=10))].copy()
            if not mom_df.empty:
                mom_df['差值'] = (mom_df['日期'] - one_month).abs()
                closest_mom_row = mom_df.loc[mom_df['差值'].idxmin()]
                mom = (now_val - closest_mom_row['汇率']) / closest_mom_row['汇率'] * 100
                mom_date = closest_mom_row['日期'].strftime('%Y-%m-%d')
            else:
                mom = np.nan
                mom_date = None

            # YoY
            one_year = now - pd.DateOffset(years=1)
            yoy_df = df[(df['日期'] >= one_year - pd.Timedelta(days=10)) & (df['日期'] <= one_year + pd.Timedelta(days=10))].copy()
            if not yoy_df.empty:
                yoy_df['差值'] = (yoy_df['日期'] - one_year).abs()
                closest_yoy_row = yoy_df.loc[yoy_df['差值'].idxmin()]
                yoy = (now_val - closest_yoy_row['汇率']) / closest_yoy_row['汇率'] * 100
                yoy_date = closest_yoy_row['日期'].strftime('%Y-%m-%d')
            else:
                yoy = np.nan
                yoy_date = None

            # 5年均值和时间范围
            five_years_ago = now - pd.DateOffset(years=5)
            five_year_df = df[df['日期'] >= five_years_ago]
            avg5 = five_year_df['汇率'].mean()
            if not five_year_df.empty:
                start_date = five_year_df['日期'].min().strftime('%Y-%m')
                end_date = five_year_df['日期'].max().strftime('%Y-%m')
                avg5_range = f"{start_date} to {end_date}"
            else:
                avg5_range = None

            results.append({
                '货币汇率': name,
                '数据源': df.attrs.get("data_source", "unknown"),
                '汇率值': now_val,
                '日期': now.strftime('%Y-%m-%d'),
                'MoM(%)': mom,
                'MoM参考日期': mom_date,
                'YoY(%)': yoy,
                'YoY参考日期': yoy_date,
                '5年均值': avg5,
                '5年均值周期': avg5_range
            })
        except Exception as e:
            if str(e) != "empty dataframe":
                logging.error(f"{name} 指标计算失败: {e}")
            results.append({
                '货币汇率': name,
                '数据源': df.attrs.get("data_source", "unavailable"),
                '汇率值': np.nan,
                '日期': None,
                'MoM(%)': np.nan,
                'MoM参考日期': None,
                'YoY(%)': np.nan,
                'YoY参考日期': None,
                '5年均值': np.nan,
                '5年均值周期': None
            })
    return pd.DataFrame(results)



def plot_trend(data_dict, years=2):
    plt.figure(figsize=(10, 6))
    now = pd.Timestamp.today()
    for name, df in data_dict.items():
        df = df[df['日期'] >= now - pd.DateOffset(years=years)].sort_values('日期')
        dfm = df.set_index('日期').resample('ME').last().dropna().reset_index()
        if not dfm.empty:
            plt.plot(dfm['日期'], dfm['汇率'], label=name)
    plt.title(f"近{years}年汇率走势")
    plt.xlabel("日期"); plt.ylabel("汇率")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xticks(rotation=45); plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.legend(); plt.tight_layout()
    plt.savefig("output/fx_trend_2y.png", dpi=300)
    plt.close()

def main(debug = False):
    print("=" * 40)
    print("货币汇率分析 USD/CNH、USD/HKD、CNH/HKD")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 40)

    # 获取汇率数据
    fx_data = {}
    for name, code in SYMBOLS.items():
        fx_data[name] = get_fx_data(code)
    fx_data = _harmonize_pair_sources(fx_data)
    fx_data['CNH_HKD'] = compute_cross_rate(fx_data['USD_CNH'], fx_data['USD_HKD'])

    # 保存数据
    save_raw_data(fx_data)

    # 计算指标
    metrics_df = calculate_metrics(fx_data)
    # 删去 MoM参考日期 和 YoY参考日期 列（兼容不同列名编码情况）
    try:
        drop_cols = [
            c for c in metrics_df.columns
            if ("MoM" in str(c) and "参考" in str(c)) or ("YoY" in str(c) and "参考" in str(c))
        ]
        if drop_cols:
            metrics_df = metrics_df.drop(columns=drop_cols, errors='ignore')
    except Exception:
        pass
    metrics_df.to_excel("output/fx_metrics.xlsx", index=False)
    print(metrics_df)

    # 可视化
    # plot_trend(fx_data)


if __name__ == "__main__":
    main()
