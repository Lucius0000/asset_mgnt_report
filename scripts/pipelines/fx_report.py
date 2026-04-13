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


def get_fx_data(symbol_code):
    try:
        df = ak.forex_hist_em(symbol=symbol_code)
    except Exception as e:
        if _looks_like_proxy_failure(e):
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
        return pd.DataFrame(columns=['日期', '汇率'])

    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    df = df[['日期', '最新价']].rename(columns={'最新价': '汇率'}).dropna()
    if df.empty:
        logging.warning(f"{symbol_code} 历史数据在清洗后为空。")
        return _get_fx_data_yfinance(symbol_code)
    return df


def _get_fx_data_yfinance(symbol_code):
    ticker = YAHOO_SYMBOLS.get(symbol_code)
    if not ticker:
        return pd.DataFrame(columns=['日期', '汇率'])
    try:
        with _without_proxy_env():
            df = yf.download(
                ticker,
                period="10y",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
    except Exception as exc:
        logging.error(f"拉取 {symbol_code} 的 Yahoo Finance 备用数据失败: {exc}")
        return pd.DataFrame(columns=['日期', '汇率'])
    if df is None or df.empty:
        logging.warning(f"{symbol_code} 的 Yahoo Finance 备用数据为空。")
        return pd.DataFrame(columns=['日期', '汇率'])
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
        return _load_cached_fx_data(symbol_code)
    logging.info(f"{symbol_code} 已切换到 Yahoo Finance 备用数据源。")
    return cleaned


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
    return cached

def compute_cross_rate(base_df, quote_df):
    if base_df.empty or quote_df.empty:
        logging.warning("交叉汇率计算跳过：基础汇率或报价汇率为空。")
        return pd.DataFrame(columns=['日期', '汇率'])
    df = pd.merge(base_df, quote_df, on='日期', suffixes=('_base', '_quote'))
    df['汇率'] = df['汇率_quote'] / df['汇率_base']
    return df[['日期', '汇率']]

def save_raw_data(data_dict):
    for name, df in data_dict.items():
        df.to_excel(f"{RAW_DATA_DIR}/{name}.xlsx", index=False)

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
