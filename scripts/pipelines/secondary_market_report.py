#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import yfinance as yf
import yfinance.cache as yf_cache
from dateutil.relativedelta import relativedelta  # 需要安装: pip install python-dateutil
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.config.inputs import parse_bool, resolve_config_value
from src.asset_mgnt_report.metrics.annualization import annualized_return_from_returns
from src.asset_mgnt_report.metrics.sharpe import sharpe_ratio as shared_sharpe_ratio
from src.asset_mgnt_report.metrics.volatility import annualized_volatility

APP_CONFIG = build_app_config(project_root=PROJECT_ROOT)
# 顶部配置区（适合 Spyder 直接运行）
# - market_mode: 字符串，候选值为 us / china / hk / mixed
# - use_default_dates: 布尔值，True / False
# - start_date / end_date: 字符串或 datetime，格式 YYYY-MM-DD，例如 2026-03-14
CONFIG = {
    "market_mode": None,
    "use_default_dates": None,
    "start_date": None,
    "end_date": None,
    "retry_attempts": 1,
    "max_workers": 6,
}

NO_FILL_HEADERS = {"Symbol", "收盘"}

INTRO_TEXT = """
由于传入 yfinance 的 end_date 为开区间，需要选择周六为 end_date，方可获取周五数据;
且由于时区的影响，美股数据推荐使用周日为 end_date;
由于是按照收盘价计算两周变动的，所以应该是取两周前的周五收盘价与当周周五收盘价比较、计算。
综上，start_date 应为两周前周五，end_date 应为当周周日，如 10.24 - 11.09
"""


def _print_intro() -> None:
    print(INTRO_TEXT)


def _refresh_runtime_config():
    global APP_CONFIG
    APP_CONFIG = build_app_config(project_root=PROJECT_ROOT)
    _configure_yfinance_cache()
    yf.set_config(proxy=_get_yfinance_proxy())
    return APP_CONFIG


def _configure_yfinance_cache() -> None:
    cache_dir = APP_CONFIG.raw_output_dir / "yfinance_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf_cache.set_cache_location(str(cache_dir))
    yf_cache.set_tz_cache_location(str(cache_dir))


def _get_yfinance_proxy() -> str | None:
    if not APP_CONFIG.use_proxy:
        return None
    return APP_CONFIG.https_proxy or APP_CONFIG.http_proxy or None


def _make_ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol)


def _download_market_data(symbol: str, start_date, end_date) -> pd.DataFrame:
    kwargs = {
        "start": start_date,
        "end": end_date,
        "auto_adjust": False,
        "progress": False,
        "timeout": 30,
    }
    try:
        return yf.download(symbol, multi_level_index=False, **kwargs)
    except TypeError:
        return yf.download(symbol, **kwargs)


def _normalize_history_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    if isinstance(normalized.index, pd.MultiIndex):
        normalized = normalized.droplevel(list(range(normalized.index.nlevels - 1)))
    if isinstance(normalized.columns, pd.MultiIndex):
        for level in reversed(range(normalized.columns.nlevels)):
            if not isinstance(normalized.columns, pd.MultiIndex):
                break
            if normalized.columns.get_level_values(level).nunique() == 1:
                normalized.columns = normalized.columns.droplevel(level)
    if getattr(normalized.index, "tz", None) is not None:
        normalized.index = normalized.index.tz_localize(None)
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.sort_index()


def _safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _collect_ticker_metadata(ticker: yf.Ticker) -> tuple[dict, dict]:
    fast_info: dict = {}
    info: dict = {}

    try:
        raw_fast_info = ticker.fast_info
        if raw_fast_info:
            for key in ("currency", "exchange", "lastPrice", "marketCap", "shares"):
                try:
                    value = raw_fast_info.get(key)
                except Exception:
                    value = None
                if value is not None:
                    fast_info[key] = value
    except Exception:
        pass

    try:
        raw_info = ticker.info
        if isinstance(raw_info, dict):
            info = raw_info
    except Exception:
        info = {}

    return fast_info, info


def _fetch_analysis_context(symbol: str, end_date: datetime | None) -> dict:
    ticker = _make_ticker(symbol)
    effective_end = end_date or datetime.now()
    analysis_start = effective_end - timedelta(days=430)
    buffer_start, buffer_end = get_market_adjusted_date_range(analysis_start, effective_end, symbol)
    history = _normalize_history_frame(
        ticker.history(start=buffer_start, end=buffer_end, auto_adjust=False)
    )
    fast_info, info = _collect_ticker_metadata(ticker)
    return {
        "history": history,
        "fast_info": fast_info,
        "info": info,
    }


def _resolve_market_cap_from_context(context: dict, latest_close: float | None) -> float | None:
    fast_info = context.get("fast_info", {})
    info = context.get("info", {})

    market_cap = _safe_float(fast_info.get("marketCap"))
    if market_cap is None:
        market_cap = _safe_float(info.get("marketCap"))
    if market_cap is not None:
        return market_cap / 1e8

    shares = _safe_float(info.get("sharesOutstanding"))
    if shares is None:
        shares = _safe_float(fast_info.get("shares"))

    price = latest_close
    if price is None:
        price = _safe_float(fast_info.get("lastPrice"))
    if price is None:
        price = _safe_float(info.get("currentPrice"))

    if shares is not None and price is not None:
        return shares * price / 1e8
    return None


def _resolve_dividend_yield_from_context(context: dict) -> float | None:
    info = context.get("info", {})
    for field in ("dividendYield", "trailingAnnualDividendYield", "yield"):
        value = _safe_float(info.get(field))
        if value is not None:
            return value
    return None


def _get_latest_close_from_history(df: pd.DataFrame | None) -> float | None:
    if df is None or df.empty:
        return None
    return _safe_float(safe_get_first(df["Close"].iloc[-1]))


def _sanitize_sheet_title(title: str) -> str:
    sanitized = re.sub(r'[\\/*?:\[\]]', "_", title).strip()
    sanitized = sanitized.replace("-", "_")
    sanitized = sanitized or "Sheet"
    return sanitized[:31]


def infer_market_region(ticker: str) -> str:
    if ticker.endswith('.HK'):
        return '港股'
    if ticker.endswith(('.SS', '.SZ')):
        return '中国A股'
    return '美股'


def adjust_date_for_market(date, symbol):
    """
    根据不同市场调整日期，处理时区差异
    
    时区问题说明：
    - 用户在北京时间输入日期（UTC+8）
    - yfinance默认按照各市场的本地时间处理：
      * 美股：美国东部时间（UTC-5/-4）
      * 港股：香港时间（UTC+8，与北京时间相同）
      * A股：北京时间（UTC+8）
    
    解决方案：
    - 美股：向前推1天，确保获取到正确的美国交易日数据
    - 港股/A股：不需要调整，时区相同
    """
    if symbol.endswith('.HK'):
        # 港股：使用香港时间，与北京时间相同 (UTC+8)
        return date
    elif symbol.endswith(('.SS', '.SZ')):
        # A股：使用北京时间 (UTC+8)
        return date
    else:
        # 美股：需要考虑时区差异
        # 北京时间比美国东部时间快12-13小时
        # 当用户输入北京时间5号时，美国时间可能还是4号
        # 为确保获取正确数据，向前推1天
        return date + timedelta(days=1)


def get_market_adjusted_date_range(start_date, end_date, symbol):
    """
    获取针对特定市场调整后的日期范围
    """
    adjusted_start = adjust_date_for_market(start_date, symbol)
    adjusted_end = adjust_date_for_market(end_date, symbol)

    # 为了确保获取足够的数据，稍微扩大范围
    buffer_start = adjusted_start - timedelta(days=3)
    buffer_end = adjusted_end + timedelta(days=3)

    return buffer_start, buffer_end


# 建议通过环境变量来获取数据库连接信息
conn_info = {
    'dbname': os.getenv('DB_NAME', 'ibkr_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '441322191139'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

# 美股标的分类
us_market_symbols = {
    # 股票-大盘
    'SPY': 'SPY',

    # 股票-行业-科技
    'QQQ': 'QQQ',

    # 股票-个股-七巨头
    'AMZN': 'AMZN',
    'GOOG': 'GOOG',
    'AAPL': 'AAPL',
    'MSFT': 'MSFT',
    'META': 'META',
    'TSLA': 'TSLA',
    'NVDA': 'NVDA',

    # 股票-个股-半导体
    'TSM': 'TSM',
    'AVGO': 'AVGO',
    'AMD': 'AMD',
    'INTC': 'INTC',
    'QCOM': 'QCOM',

    # 股票-个股-Data & AI Mgnt
    'SNOW': 'SNOW',
    'ORCL': 'ORCL',
    'MDB': 'MDB',
    'PLTR': 'PLTR',
    'DDOG': 'DDOG',

    # 股票-个股-SaaS
    'CRM': 'CRM',
    'APP': 'APP',
    'ADBE': 'ADBE',
    'NOW': 'NOW',
    'WDAY': 'WDAY',

    # 股票-个股-中概
    'BABA': 'BABA',
    'PDD': 'PDD',
    'JD': 'JD',
    'BIDU': 'BIDU',
    'NTES': 'NTES',

    # 债券-大盘
    'BND': 'BND',
    'AGG': 'AGG'
}

us_categories = {
    '大盘': ['SPY'],
    '行业-科技': ['QQQ'],
    '个股-七巨头': ['AMZN', 'GOOG', 'AAPL', 'MSFT', 'META', 'TSLA', 'NVDA'],
    '个股-半导体': ['NVDA', 'TSM', 'AVGO', 'AMD', 'INTC', 'QCOM'],
    '个股-Data & AI Mgnt': ['SNOW', 'ORCL', 'MDB', 'PLTR', 'DDOG'],
    '个股-SaaS': ['CRM', 'APP', 'ADBE', 'NOW', 'WDAY'],
    '个股-中概': ['BABA', 'PDD', 'JD', 'BIDU', 'NTES'],
    '债券-大盘': ['BND', 'AGG']
}

# 中国A股标的分类
china_market_symbols = {
    '华泰柏瑞沪深300ETF': '510300.SS',
    '华夏科创50ETF': '588000.SS',
    '南方中证500ETF': '510500.SS',
    '南方中证1000ETF': '512100.SS',
    '贵州茅台': '600519.SS',
    '伊利股份': '600887.SS',
    '美的集团': '000333.SZ',
    '工商银行': '601398.SS',
    '中国平安': '601318.SS',
    '比亚迪A': '002594.SZ',
    '宁德时代': '300750.SZ',
    '隆基绿能': '601012.SS',
    '中芯国际A': '688981.SS',
    '寒武纪': '688256.SS',
    '海光信息': '688041.SS',
    '兆易创新': '603986.SS',
    '中科曙光': '603019.SS',
    '工业富联': '601138.SS',
    '中兴通讯': '000063.SZ',
    '金山办公': '688111.SS',
    '科大讯飞': '002230.SZ',
    '用友网络': '600588.SS',
    '中国移动': '600941.SS',
    '中国电信': '601728.SS',
    '中国联通': '600050.SS',
    '紫金矿业': '601899.SS',
    '洛阳钼业': '603993.SS',
    '红利低波ETF': '512890.SS',
    '国信价值ETF': '512040.SS',
    '中证红利': '515180.SS',
    '深证红利ETF': '159905.SZ',
    '科创成长50ETF': '588020.SS',
    '沪深300成长ETF': '562310.SS',
    '平安MSCI中国A股低波ETF': '512390.SS',
}

china_categories = {
    '大盘': ['华泰柏瑞沪深300ETF', '华夏科创50ETF'],
    '个股-消费': ['贵州茅台', '伊利股份', '美的集团'],
    '个股-金融': ['工商银行', '中国平安'],
    '个股-新能源': ['比亚迪A', '宁德时代', '隆基绿能'],
    '个股-半导体/算力': ['中芯国际A', '寒武纪', '海光信息', '兆易创新', '中科曙光', '工业富联', '中兴通讯'],
    '个股-软件': ['金山办公', '科大讯飞', '用友网络'],
    '个股-云基础设施': ['中国移动', '中国电信', '中国联通'],
    '个股-金属': ['紫金矿业', '洛阳钼业'],
    'Smart Beta-中盘': ['南方中证500ETF'],
    'Smart Beta-小盘': ['南方中证1000ETF'],
    'Smart Beta-红利低波': ['红利低波ETF'],
    'Smart Beta-价值': ['国信价值ETF'],
    'Smart Beta-红利': ['中证红利', '深证红利ETF'],
    'Smart Beta-成长': ['科创成长50ETF', '沪深300成长ETF'],
    'Smart Beta-低波': ['平安MSCI中国A股低波ETF'],
}

# 港股标的分类
hk_market_symbols = {
    '恒生指数盈富基金': '2800.HK',
    # '中证香港300本地股ETF': '',  # 需要确认具体代码
    '华夏恒生科技ETF': '3032.HK',  # 使用港股代码
    '平安香港高息ETF': '3070.HK',
    '恒生高息股30ETF': '3466.HK',
    # '惠理高息股票基金': '',  # 需要确认具体代码
    '汇丰控股': '0005.HK',
    '友邦保险': '1299.HK',
    '新鸿基地产': '0016.HK',
    '领展房产基金': '0823.HK',
    '中电控股': '0002.HK',
    '香港中华煤气': '0003.HK',
    '中广核电力': '1816.HK',
    '中海油': '0883.HK',
    '腾讯控股': '0700.HK',
    '阿里巴巴': '9988.HK',
    '美团': '3690.HK',
    '比亚迪H': '1211.HK',
    '中芯国际H': '0981.HK',
}

hk_categories = {
    '大盘': ['恒生指数盈富基金'],
    '行业-科技': ['华夏恒生科技ETF'],
    '个股-金融': ['汇丰控股', '友邦保险'],
    '个股-地产': ['新鸿基地产', '领展房产基金'],
    '个股-公用事业': ['中电控股', '香港中华煤气'],
    '个股-能源': ['中广核电力', '中海油'],
    '个股-互联网': ['腾讯控股', '阿里巴巴', '美团'],
    '个股-新能源': ['比亚迪H'],
    '个股-半导体': ['中芯国际H'],
    'Smart Beta-红利': ['平安香港高息ETF', '恒生高息股30ETF'],
}


def _merge_symbol_maps(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for symbol_map in maps:
        merged.update(symbol_map)
    return merged


def _merge_category_maps(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for category_map in maps:
        for category, symbols in category_map.items():
            bucket = merged.setdefault(category, [])
            for symbol in symbols:
                if symbol not in bucket:
                    bucket.append(symbol)
    return merged


def _prefix_category_names(region: str, category_map: dict[str, list[str]]) -> dict[str, list[str]]:
    return {f"{region}-{category}": list(symbols) for category, symbols in category_map.items()}


def _build_mixed_categories() -> dict[str, list[str]]:
    return _merge_category_maps(
        us_categories,
        _prefix_category_names("中国A股", china_categories),
        _prefix_category_names("港股", hk_categories),
    )


MARKET_MODE_SPECS = {
    'us': {
        'symbols': us_market_symbols,
        'categories': us_categories,
        'market_type': '美股',
        'report_prefix': 'us_market_report',
    },
    'china': {
        'symbols': china_market_symbols,
        'categories': china_categories,
        'market_type': '中国A股',
        'report_prefix': 'china_market_report',
    },
    'hk': {
        'symbols': hk_market_symbols,
        'categories': hk_categories,
        'market_type': '港股',
        'report_prefix': 'hk_market_report',
    },
    'mixed': {
        'symbols': _merge_symbol_maps(us_market_symbols, china_market_symbols, hk_market_symbols),
        'categories': _build_mixed_categories(),
        'market_type': '混合',
        'report_prefix': 'mixed_market_report',
    },
}


def safe_get_first(value):
    """统一处理可能为列表、Series等类型的数据，返回第一个有效值。"""
    if isinstance(value, (list, tuple)):
        return value[1] if len(value) > 1 else value[0]
    elif isinstance(value, pd.Series):
        return value.iloc[0]
    return value


def get_date_input(prompt):
    """获取用户输入的日期，并进行格式和逻辑校验"""
    while True:
        try:
            print(f"\n📅 输入{prompt}:")
            year = int(input("请输入年份 (如2024): "))

            # 年份合理性检查
            if year < 1900 or year > datetime.now().year:
                print(f"年份应该在1900到{datetime.now().year}之间，请重新输入。")
                continue

            month = int(input("请输入月份 (1-12): "))
            if month < 1 or month > 12:
                print("月份应该在1到12之间，请重新输入。")
                continue

            day = int(input("请输入日期 (1-31): "))
            if day < 1 or day > 31:
                print("日期应该在1到31之间，请重新输入。")
                continue

            date = datetime(year, month, day)

            # 检查日期不能是未来日期
            if date > datetime.now():
                print("❌ 错误：不能输入未来的日期，请重新输入。")
                continue

            # 检查日期不能过于久远（超过20年）
            twenty_years_ago = datetime.now() - timedelta(days=365 * 20)
            if date < twenty_years_ago:
                print(f"⚠️  警告：输入的日期过于久远（{date.strftime('%Y-%m-%d')}），可能无法获取到准确的金融数据。")
                confirm = input("是否继续使用此日期？(y/n): ").strip().lower()
                if confirm not in ['y', 'yes', '是']:
                    continue

            print(
                f"✅ {prompt}已确认：{date.strftime('%Y-%m-%d')}({['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date.weekday()]})")
            return date

        except ValueError as e:
            print(f"❌ 输入的日期无效：{e}，请重新输入。")


def get_default_dates():
    """
    获取默认的金融分析日期范围
    
    逻辑：
    - end_date: 本周六（确保包含本周五的交易数据）
    - start_date: 上上周五（标准的两周分析起点）
    
    这样设计的原因：
    1. 金融市场交易周是周一到周五
    2. 周六作为结束日期确保包含本周五的数据
    3. 与用户验证的模式一致：周五→周六的数据能计算正确的两周变动
    4. 不受运行脚本具体时间影响，结果稳定
    """
    today = datetime.now()
    current_weekday = today.weekday()  # 0=周一, 1=周二, ..., 5=周六, 6=周日

    # 计算本周六作为 end_date
    if current_weekday == 5:  # 今天是周六
        end_date = today
    elif current_weekday == 6:  # 今天是周日
        end_date = today - timedelta(days=1)  # 昨天是周六
    else:  # 周一到周五
        days_until_saturday = 5 - current_weekday
        end_date = today + timedelta(days=days_until_saturday)

    # 计算上上周五作为 start_date（从本周六向前推15天）
    start_date = end_date - timedelta(days=15)

    # 验证start_date确实是周五，如果不是则调整
    while start_date.weekday() != 4:  # 4 = 周五
        start_date -= timedelta(days=1)

    return start_date, end_date


def resolve_market_selection(market_mode: str | None = None) -> tuple[dict[str, str], dict[str, list[str]], str, str]:
    normalized = (market_mode or "").strip().lower()
    mapping = {
        "1": "us",
        "us": "us",
        "美股": "us",
        "2": "china",
        "china": "china",
        "a股": "china",
        "中国a股": "china",
        "中国a": "china",
        "中国": "china",
        "3": "hk",
        "hk": "hk",
        "港股": "hk",
        "4": "mixed",
        "mixed": "mixed",
        "混合": "mixed",
    }
    selected = mapping.get(normalized)
    if selected is None:
        print("选择市场模式：")
        print("1. 美股模式")
        print("2. 中国A股模式")
        print("3. 港股模式")
        print("4. 混合模式（美股+A股+港股）")
        selected = mapping.get(input("请选择 (1、2、3 或 4): ").strip(), "mixed")

    spec = MARKET_MODE_SPECS[selected]
    return spec["symbols"], spec["categories"], spec["market_type"], spec["report_prefix"]


def resolve_date_selection(
    use_default_dates: bool | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
) -> tuple[datetime, datetime]:
    def _coerce(value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    start = _coerce(start_date)
    end = _coerce(end_date)

    if start is not None and end is not None:
        if start >= end:
            raise ValueError("开始日期必须早于结束日期。")
        return start, end

    if use_default_dates is True:
        return get_default_dates()

    if use_default_dates is False:
        print("请手动输入日期")
        start = get_date_input("开始日期")
        end = get_date_input("结束日期")
    else:
        print("选择日期输入方式：")
        print("1. 使用智能默认日期（上周五→本周六）")
        print("2. 手动输入日期")
        choice = input("请选择 (1 或 2): ").strip()
        if choice == "1":
            start, end = get_default_dates()
            weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            print(
                f"使用智能默认日期：{start.strftime('%Y-%m-%d')}({weekday_names[start.weekday()]}) 到 {end.strftime('%Y-%m-%d')}({weekday_names[end.weekday()]})"
            )
            return start, end
        print("请手动输入日期")
        start = get_date_input("开始日期")
        end = get_date_input("结束日期")

    while start >= end:
        print("错误：开始日期必须早于结束日期！")
        print(f"当前输入：开始日期 {start.strftime('%Y-%m-%d')}，结束日期 {end.strftime('%Y-%m-%d')}")
        print("请选择要修改的日期：")
        print("1. 修改开始日期")
        print("2. 修改结束日期")
        print("3. 重新输入全部日期")
        modify_choice = input("请选择 (1、2 或 3): ").strip()
        if modify_choice == "1":
            start = get_date_input("开始日期")
        elif modify_choice == "2":
            end = get_date_input("结束日期")
        else:
            start = get_date_input("开始日期")
            end = get_date_input("结束日期")

    print(f"[OK] 确认日期范围：{start.strftime('%Y-%m-%d')} 到 {end.strftime('%Y-%m-%d')}")
    print(f"  分析时间跨度：{(end - start).days} 天")
    return start, end


def get_weekly_data(symbols, start_date, end_date):
    """下载指定符号的历史数据，并对失败项集中重试。"""
    data: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    ordered_items = list(symbols.items())
    total_symbols = len(ordered_items)
    retry_attempts = _coerce_int(CONFIG.get("retry_attempts"), 1)

    print(f"\n开始下载 {total_symbols} 个符号的数据...")

    def _download_one(item: tuple[str, str]) -> tuple[str, str, pd.DataFrame, str | None]:
        name, symbol = item
        try:
            df = _normalize_history_frame(_download_market_data(symbol, start_date, end_date))
            if df.empty:
                return name, symbol, df, "指定日期范围内无数据"
            return name, symbol, df, None
        except Exception as exc:
            return name, symbol, pd.DataFrame(), str(exc)

    def _run_round(items: list[tuple[str, str]], round_label: str) -> dict[str, str]:
        round_failures: dict[str, str] = {}
        for index, item in enumerate(items, start=1):
            name, symbol, df, error = _download_one(item)
            prefix = f"[{round_label} {index}/{len(items)}]"
            print(f"{prefix} {name} ({symbol})")
            if error is None:
                data[name] = df
                print(f"  [OK] 成功获取 {len(df)} 条数据")
            else:
                round_failures[name] = error
                print(f"  [FAIL] 获取失败: {error}")
        return round_failures

    pending_items = ordered_items
    failures = _run_round(pending_items, "首次")

    for attempt in range(1, retry_attempts + 1):
        if not failures:
            break
        failed_items = [(name, symbol) for name, symbol in ordered_items if name in failures]
        print(f"\n开始第 {attempt} 次集中重试，待重试标的数: {len(failed_items)}")
        failures = _run_round(failed_items, f"重试{attempt}")

    ordered_data = {
        name: data[name]
        for name, _symbol in ordered_items
        if name in data
    }

    if failures:
        print("\n以下标的在全部重试后仍获取失败：")
        for name, error in failures.items():
            print(f"  - {name} ({symbols[name]}): {error}")

    print(f"数据下载完成！成功获取 {len(ordered_data)} 个符号的数据。\n")
    return ordered_data


# 添加新的标准化指标计算函数
def get_standardized_two_week_change(symbol: str, df=None, start_date=None, end_date=None) -> float:
    """
    计算标准的两周变动率

    参数:
    - symbol: 股票代码
    - df: 已下载的数据，如果提供则优先使用
    - start_date: 开始日期，如果提供则计算从 start_date 到 end_date 的变动率
    - end_date: 结束日期

    逻辑:
    1. 如果提供了 df 和 start_date，即手动选择日期，使用指定日期范围计算变动率
    2. 否则（即智能日期选择）按两周前的交易日回溯计算
    """
    try:
        if df is not None and start_date is not None:
            if df.empty or len(df) < 2:
                print(f"警告：{symbol} 的数据不足，无法计算变动率")
                return 0

            start_price = df.iloc[0]['Close']
            end_price = df.iloc[-1]['Close']

            change = ((end_price - start_price) / start_price) * 100
            return change

        ticker = _make_ticker(symbol)
        if end_date is None:
            end_date = datetime.now()

        start_date_auto = end_date - timedelta(days=31)
        buffer_start, buffer_end = get_market_adjusted_date_range(start_date_auto, end_date, symbol)

        data = ticker.history(start=buffer_start, end=buffer_end, auto_adjust=False)

        if data.empty or len(data) < 2:
            print(f"警告：无法获取 {symbol} 的两周变动数据")
            return 0

        current_price = data.iloc[-1]['Close']
        current_date = data.index[-1]

        two_weeks_ago_price = None
        target_trading_days = [10, 11, 9, 12, 13]

        for trading_days in target_trading_days:
            if len(data) >= trading_days + 1:
                candidate_price = data.iloc[-(trading_days + 1)]['Close']
                candidate_date = data.index[-(trading_days + 1)]

                days_diff = (current_date.date() - candidate_date.date()).days
                if 9 <= days_diff <= 16:
                    two_weeks_ago_price = candidate_price
                    break

        if two_weeks_ago_price is None:
            if len(data) >= 13:
                two_weeks_ago_price = data.iloc[-13]['Close']
            elif len(data) >= 11:
                two_weeks_ago_price = data.iloc[-11]['Close']
            elif len(data) >= 2:
                two_weeks_ago_price = data.iloc[0]['Close']
            else:
                return 0

        two_week_change = ((current_price - two_weeks_ago_price) / two_weeks_ago_price) * 100

        return two_week_change

    except Exception as e:
        print(f"计算两周变动时出错：{symbol}，错误：{e}")
        return 0

def get_standardized_ytd(symbol: str, end_date: datetime = None) -> float:
    """
    计算标准的年初至今收益率 (YTD)。
    该方法使用上一年最后一个交易日的收盘价作为计算基准，这是最标准的做法。
    """
    if end_date is None:
        end_date = datetime.now()

    # 1. 确定获取数据的日期范围
    # 为了确保能获取到上一年最后一个交易日，我们将开始日期设为上一年的12月20日左右
    start_of_fetch_range = datetime(end_date.year - 1, 12, 20)

    try:
        # 2. 获取数据
        ticker = _make_ticker(symbol)
        # 我们获取从去年年底到指定结束日期的数据
        data = ticker.history(start=start_of_fetch_range, end=end_date + timedelta(days=1), auto_adjust=False)

        if data.empty:
            print(f"警告：无法获取 {symbol} 在指定日期范围的历史数据。")
            return 0.0

        # 3. 找到上一年最后一个交易日的收盘价 (起始价格)
        prev_year_data = data[data.index.year == end_date.year - 1]
        if prev_year_data.empty:
            print(f"警告：找不到 {symbol} 在 {end_date.year - 1} 年的交易数据。")
            return 0.0

        # 上一年最后一个交易日的收盘价即为我们的起始价格
        start_price = prev_year_data['Close'].iloc[-1]
        start_price_date = prev_year_data.index[-1].date()

        # 4. 找到 end_date 或之前最近的交易日收盘价 (当前价格)
        current_year_data = data[data.index.year == end_date.year]
        # 筛选出不晚于 end_date 的数据
        current_year_data = current_year_data[current_year_data.index.date <= end_date.date()]
        if current_year_data.empty:
            print(f"警告：找不到 {symbol} 在 {end_date.year} 年截至 {end_date.date()} 的交易数据。")
            return 0.0

        current_price = current_year_data['Close'].iloc[-1]
        current_price_date = current_year_data.index[-1].date()

        print(f"计算 {symbol} YTD:")
        print(f" - 起始日期 (上年收盘): {start_price_date}, 价格: {start_price:.2f}")
        print(f" - 结束日期 (当前): {current_price_date}, 价格: {current_price:.2f}")

        # 5. 计算 YTD 收益率
        if start_price == 0:
            print(f"警告：起始价格为0，无法计算YTD。")
            return 0.0

        ytd_return = ((current_price - start_price) / start_price) * 100
        return ytd_return

    except Exception as e:
        print(f"计算YTD时出错：{symbol}，错误：{e}")
        return 0.0


def get_standardized_mom(symbol: str, end_date=None) -> float:
    """
    计算基于日历的精确月环比收益率 (MoM)。
    """
    if end_date is None:
        end_date = datetime.now().date()
    else:
        end_date = end_date.date()

    # 1. 定义查找范围
    # 获取额外的数据以确保能找到目标日期
    fetch_start_date = end_date - timedelta(days=45)

    try:
        # 2. 获取历史数据
        ticker = _make_ticker(symbol)
        data = ticker.history(start=fetch_start_date, end=end_date + timedelta(days=1), auto_adjust=False)

        if data.empty or len(data) < 2:
            print(f"警告：无法获取 {symbol} 的MoM数据")
            return 0.0

        # 将索引转换为日期，方便比较
        data.index = data.index.date

        # 3. 确定当前价格和目标日期
        current_price_series = data[data.index <= end_date]
        if current_price_series.empty:
            print(f"警告：找不到 {symbol} 在 {end_date} 或之前的价格。")
            return 0.0
        current_price = current_price_series['Close'].iloc[-1]
        current_date = current_price_series.index[-1]

        # 计算一个月前的目标日期
        target_date_1m_ago = current_date - relativedelta(months=1)

        # 4. 寻找一个月前最接近的实际交易日价格
        # 从数据中筛选出所有早于或等于目标日期的记录
        past_data = data[data.index <= target_date_1m_ago]
        if past_data.empty:
            print(f"警告：找不到 {symbol} 在 {target_date_1m_ago} 或之前的足够历史数据。")
            return 0.0  # 或者返回 None 表示无法计算

        month_ago_price = past_data['Close'].iloc[-1]
        month_ago_date = past_data.index[-1]

        print(f"计算 {symbol} MoM:")
        print(f" - 起始日期: {month_ago_date}, 价格: {month_ago_price:.2f}")
        print(f" - 结束日期: {current_date}, 价格: {current_price:.2f}")

        # 5. 计算收益率
        return ((current_price - month_ago_price) / month_ago_price) * 100

    except Exception as e:
        print(f"计算MoM时出错：{symbol}，错误：{e}")
        return 0.0


def get_standardized_yoy(symbol: str, end_date: datetime = None) -> float:
    #    """
    #     计算基于日历的精确年同比收益率 (YoY)。
    #     """
    if end_date is None:
        end_date = datetime.now().date()
    else:
        end_date = end_date.date()

    # 1. 定义查找范围 (一年大约365天，加一些缓冲)
    fetch_start_date = end_date - timedelta(days=380)

    try:
        # 2. 获取历史数据
        ticker = _make_ticker(symbol)
        data = ticker.history(start=fetch_start_date, end=end_date + timedelta(days=1), auto_adjust=False)

        if data.empty or len(data) < 2:
            print(f"警告：无法获取 {symbol} 的YoY数据")
            return 0.0

        data.index = data.index.date

        # 3. 确定当前价格和目标日期
        current_price_series = data[data.index <= end_date]
        if current_price_series.empty:
            print(f"警告：找不到 {symbol} 在 {end_date} 或之前的价格。")
            return 0.0
        current_price = current_price_series['Close'].iloc[-1]
        current_date = current_price_series.index[-1]

        # 计算一年前的目标日期
        target_date_1y_ago = current_date - relativedelta(years=1)

        # 4. 寻找一年前最接近的实际交易日价格
        past_data = data[data.index <= target_date_1y_ago]
        if past_data.empty:
            print(f"警告：找不到 {symbol} 在 {target_date_1y_ago} 或之前的足够历史数据。")
            return 0.0

        year_ago_price = past_data['Close'].iloc[-1]
        year_ago_date = past_data.index[-1]

        print(f"计算 {symbol} YoY:")
        print(f" - 起始日期: {year_ago_date}, 价格: {year_ago_price:.2f}")
        print(f" - 结束日期: {current_date}, 价格: {current_price:.2f}")

        # 5. 计算收益率
        return ((current_price - year_ago_price) / year_ago_price) * 100

    except Exception as e:
        print(f"计算YoY时出错：{symbol}，错误：{e}")
        return 0.0


def get_standardized_market_cap(symbol, end_date=None):
    """计算标准市值（基于指定日期的收盘价）"""
    try:
        stock = _make_ticker(symbol)
        info = stock.info
        shares = info.get('sharesOutstanding')

        if end_date:
            # 使用时区调整的日期范围
            start_date = end_date - timedelta(days=7)
            buffer_start, buffer_end = get_market_adjusted_date_range(start_date, end_date, symbol)

            hist = stock.history(start=buffer_start, end=buffer_end, auto_adjust=False)
            if not hist.empty:
                price = hist.iloc[-1]['Close']
            else:
                price = info.get('currentPrice')
        else:
            price = info.get('currentPrice')

        if shares and price:
            # 根据不同市场计算市值
            if symbol.endswith('.HK'):
                return shares * price / 1e8  # 转换为亿港币
            elif symbol.endswith(('.SS', '.SZ')):
                return shares * price / 1e8  # 转换为亿人民币
            else:
                return shares * price / 1e8  # 美股转换为亿美元
    except Exception as e:
        print(f"获取市值时出错：{symbol}，错误：{e}")
    return None

def get_standardized_dividend_yield(symbol):
    """获取标准化的股息率（百分比）"""
    try:
        info = _make_ticker(symbol).info
        dy = info.get('dividendYield')
        if dy is not None:
            return round(dy, 2)
    except Exception as e:
        print(f"获取股息率时出错：{symbol}，错误：{e}")
    return None


def get_standardized_annualized_volatility(symbol, end_date=None, period_days=252):
    """计算标准年化波动率（基于指定日期向前推算）"""
    try:
        stock = _make_ticker(symbol)
        if end_date is None:
            end_date = datetime.now()

        # 使用时区调整的日期范围
        start_date = end_date - timedelta(days=period_days + 50)  # 多加50天确保有足够交易日
        buffer_start, buffer_end = get_market_adjusted_date_range(start_date, end_date, symbol)

        hist = stock.history(start=buffer_start, end=buffer_end, auto_adjust=False)

        if not hist.empty and len(hist) >= 20:  # 至少需要20个交易日
            # 取最近的交易日数据，最多取period_days天
            if len(hist) > period_days:
                hist = hist.tail(period_days)

            daily_return = hist['Close'].pct_change().dropna()
            if len(daily_return) > 0:
                return annualized_volatility(daily_return, periods_per_year=252)
    except Exception as e:
        print(f"计算年化波动率时出错：{symbol}，错误：{e}")
    return None


def get_standardized_sharpe_ratio(symbol, end_date=None, risk_free_rate=0.02):
    """计算标准夏普比率 - 使用1年数据"""
    try:
        stock = _make_ticker(symbol)
        if end_date is None:
            end_date = datetime.now()

        # 获取1年的历史数据（约252个交易日）
        start_date = end_date - timedelta(days=365 + 50)  # 多加50天确保有足够交易日
        buffer_start, buffer_end = get_market_adjusted_date_range(start_date, end_date, symbol)

        hist = stock.history(start=buffer_start, end=buffer_end, auto_adjust=False)

        if not hist.empty and len(hist) >= 252:  # 至少需要1年数据
            # 计算年化波动率
            daily_returns = hist['Close'].pct_change().dropna()
            if len(daily_returns) > 0:
                annualized_return = annualized_return_from_returns(daily_returns, periods_per_year=252)
                annualized_vol = annualized_volatility(daily_returns, periods_per_year=252)

                if annualized_vol != 0:
                    return shared_sharpe_ratio(annualized_return, annualized_vol, risk_free_rate)
        elif not hist.empty and len(hist) >= 60:  # 如果数据不足1年但至少有60个交易日
            # 使用可用数据计算，但给出警告
            print(f"警告：{symbol} 的历史数据不足1年（{len(hist)}个交易日），夏普比率可能不够准确")

            daily_returns = hist['Close'].pct_change().dropna()
            if len(daily_returns) > 0:
                annualized_return = annualized_return_from_returns(daily_returns, periods_per_year=252)
                annualized_vol = annualized_volatility(daily_returns, periods_per_year=252)

                if annualized_vol != 0:
                    return shared_sharpe_ratio(annualized_return, annualized_vol, risk_free_rate)
        else:
            print(f"警告：{symbol} 的历史数据不足，无法计算夏普比率")

    except Exception as e:
        print(f"计算夏普比率时出错：{symbol}，错误：{e}")
    return None


def _slice_history_to_end_date(history: pd.DataFrame, end_date: datetime | None) -> pd.DataFrame:
    normalized = _normalize_history_frame(history)
    if normalized.empty or end_date is None:
        return normalized
    return normalized[normalized.index <= pd.Timestamp(end_date)]


def _get_close_on_or_before(history: pd.DataFrame, target_date: datetime) -> tuple[float | None, datetime | None]:
    eligible = history[history.index <= pd.Timestamp(target_date)]
    if eligible.empty:
        return None, None
    return _safe_float(eligible["Close"].iloc[-1]), eligible.index[-1].to_pydatetime()


def _calculate_two_week_change_from_history(history: pd.DataFrame) -> float:
    if history.empty or len(history) < 2:
        return 0.0

    current_price = _safe_float(history.iloc[-1]["Close"])
    current_date = history.index[-1]
    if current_price is None:
        return 0.0

    target_trading_days = [10, 11, 9, 12, 13]
    two_weeks_ago_price = None

    for trading_days in target_trading_days:
        if len(history) >= trading_days + 1:
            candidate_price = _safe_float(history.iloc[-(trading_days + 1)]["Close"])
            candidate_date = history.index[-(trading_days + 1)]
            if candidate_price is None:
                continue
            days_diff = (current_date.date() - candidate_date.date()).days
            if 9 <= days_diff <= 16:
                two_weeks_ago_price = candidate_price
                break

    if two_weeks_ago_price is None:
        fallback_index = 0
        if len(history) >= 13:
            fallback_index = -13
        elif len(history) >= 11:
            fallback_index = -11
        two_weeks_ago_price = _safe_float(history.iloc[fallback_index]["Close"])

    if two_weeks_ago_price in (None, 0):
        return 0.0
    return ((current_price - two_weeks_ago_price) / two_weeks_ago_price) * 100


def _calculate_ytd_from_history(history: pd.DataFrame, end_date: datetime) -> float:
    if history.empty:
        return 0.0

    prev_year_data = history[history.index.year == end_date.year - 1]
    current_year_data = history[
        (history.index.year == end_date.year)
        & (history.index <= pd.Timestamp(end_date))
    ]
    if prev_year_data.empty or current_year_data.empty:
        return 0.0

    start_price = _safe_float(prev_year_data["Close"].iloc[-1])
    current_price = _safe_float(current_year_data["Close"].iloc[-1])
    if start_price in (None, 0) or current_price is None:
        return 0.0
    return ((current_price - start_price) / start_price) * 100


def _calculate_mom_from_history(history: pd.DataFrame, end_date: datetime) -> float:
    if history.empty:
        return 0.0

    current_price, current_trading_date = _get_close_on_or_before(history, end_date)
    if current_price is None or current_trading_date is None:
        return 0.0

    target_date = current_trading_date - relativedelta(months=1)
    month_ago_price, _ = _get_close_on_or_before(history, target_date)
    if month_ago_price in (None, 0):
        return 0.0
    return ((current_price - month_ago_price) / month_ago_price) * 100


def _calculate_yoy_from_history(history: pd.DataFrame, end_date: datetime) -> float:
    if history.empty:
        return 0.0

    current_price, current_trading_date = _get_close_on_or_before(history, end_date)
    if current_price is None or current_trading_date is None:
        return 0.0

    target_date = current_trading_date - relativedelta(years=1)
    year_ago_price, _ = _get_close_on_or_before(history, target_date)
    if year_ago_price in (None, 0):
        return 0.0
    return ((current_price - year_ago_price) / year_ago_price) * 100


def _calculate_annualized_volatility_from_history(history: pd.DataFrame, period_days: int = 252) -> float | None:
    if history.empty or len(history) < 20:
        return None
    truncated = history.tail(period_days)
    daily_returns = truncated["Close"].pct_change().dropna()
    if daily_returns.empty:
        return None
    return annualized_volatility(daily_returns, periods_per_year=252)


def _calculate_sharpe_ratio_from_history(
    history: pd.DataFrame,
    risk_free_rate: float = 0.02,
    period_days: int = 252,
) -> float | None:
    if history.empty or len(history) < 60:
        return None
    truncated = history.tail(period_days)
    daily_returns = truncated["Close"].pct_change().dropna()
    if daily_returns.empty:
        return None
    annualized_return = annualized_return_from_returns(daily_returns, periods_per_year=252)
    annualized_vol = annualized_volatility(daily_returns, periods_per_year=252)
    if annualized_vol == 0:
        return None
    return shared_sharpe_ratio(annualized_return, annualized_vol, risk_free_rate)


def calculate_indicators(df, symbol, market_symbols, market_type, start_date=None, end_date=None):
    """计算指标。"""
    _ = market_type
    latest_close = _get_latest_close_from_history(df)
    if latest_close is None:
        raise ValueError("最新收盘价缺失，无法计算指标。")

    market_symbol = market_symbols.get(symbol)
    if not market_symbol:
        raise ValueError(f"符号 {symbol} 不在市场符号列表中。")
    market_region = infer_market_region(market_symbol)
    analysis_context = _fetch_analysis_context(market_symbol, end_date)
    analysis_history = _slice_history_to_end_date(analysis_context["history"], end_date or datetime.now())

    if start_date is not None:
        first_close = _safe_float(safe_get_first(df['Close'].iloc[0]))
        if first_close in (None, 0):
            raise ValueError("初始收盘价为 0，无法计算涨跌幅。")
        two_week_return_value = (latest_close - first_close) / first_close * 100
    else:
        two_week_return_value = _calculate_two_week_change_from_history(analysis_history)

    effective_end = end_date or datetime.now()
    market_cap = _resolve_market_cap_from_context(analysis_context, latest_close)
    ytd_rate = _calculate_ytd_from_history(analysis_history, effective_end)
    mom_rate = _calculate_mom_from_history(analysis_history, effective_end)
    yoy_rate = _calculate_yoy_from_history(analysis_history, effective_end)
    sharpe_ratio = _calculate_sharpe_ratio_from_history(analysis_history)
    annual_vol = _calculate_annualized_volatility_from_history(analysis_history)
    dividend_yield = _resolve_dividend_yield_from_context(analysis_context)

    return {
        'symbol': symbol,
        'market_region': market_region,
        'two_week_return': round(two_week_return_value, 2),
        'ytd_rate': round(ytd_rate, 2),
        'mom_rate': round(mom_rate, 2),
        'yoy_rate': round(yoy_rate, 2),
        'latest_close': round(latest_close, 2),
        'market_cap': round(market_cap, 2) if market_cap is not None else None,
        'sharp_ratio': round(sharpe_ratio, 2) if sharpe_ratio is not None else None,
        'dividend_yield': round(dividend_yield, 2) if dividend_yield is not None else None,
        'annualized_volatility': round(annual_vol, 2) if annual_vol is not None else None,
    }


def get_gradient_fill(value, max_value, min_value):
    """根据数值大小生成渐变色填充"""
    if np.isnan(value) or max_value == min_value:
        color = 'FFFFFF'
    elif value > 0:
        intensity = int(150 * (value / max_value))
        color = f'FF{(210 - intensity):02X}{(210 - intensity):02X}'
    elif value < 0:
        intensity = int(210 * (abs(value) / abs(min_value)))
        color = f'{(210 - intensity):02X}FF{(210 - intensity):02X}'
    else:
        color = 'FFFFFF'
    return PatternFill(start_color=color, end_color=color, fill_type='solid')


def _column_indexes_for_headers(ws, headers: set[str]) -> set[int]:
    return {
        cell.column
        for cell in ws[1]
        if isinstance(cell.value, str) and cell.value in headers
    }


def apply_gradient_fill(ws, skip_rows=1, skip_columns=0, excluded_headers: set[str] | None = None):
    """给工作表应用渐变色填充（跳过表头和指定列）"""
    start_row = ws.min_row + skip_rows
    start_col = ws.min_column + skip_columns
    excluded_columns = _column_indexes_for_headers(ws, excluded_headers or set())

    for col_idx in range(start_col + 1, ws.max_column + 1):
        if col_idx in excluded_columns:
            continue
        col_values = []
        for row_idx in range(start_row, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if isinstance(value, (int, float)) and not np.isnan(value):
                col_values.append(float(value))
        if col_values:
            max_val, min_val = max(col_values), min(col_values)
            for row_idx in range(start_row, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                if isinstance(cell.value, (int, float)) and not np.isnan(cell.value):
                    fill = get_gradient_fill(float(cell.value), max_val, min_val)
                    cell.fill = fill


def get_category_for_symbol(symbol, categories):
    """获取符号所属的类别"""
    for category, symbols in categories.items():
        if symbol in symbols:
            return category
    return "其他"


def _ordered_data_by_categories(data: dict[str, dict], categories: dict[str, list[str]]) -> dict[str, dict]:
    ordered: dict[str, dict] = {}
    for symbols in categories.values():
        for symbol in symbols:
            if symbol in data and symbol not in ordered:
                ordered[symbol] = data[symbol]
    for symbol, values in data.items():
        if symbol not in ordered:
            ordered[symbol] = values
    return ordered


def should_include_market_region(market_type: str) -> bool:
    return market_type == "混合"


def get_market_cap_column_label(market_type: str) -> str:
    if market_type == "美股":
        return "市值(亿美元)"
    if market_type == "中国A股":
        return "市值(亿人民币)"
    if market_type == "港股":
        return "市值(亿港币)"
    return "市值(亿)"


def _format_report_frame(df: pd.DataFrame) -> pd.DataFrame:
    formatted = df.copy()
    numeric_cols = formatted.select_dtypes(include=['number']).columns
    if len(numeric_cols) > 0:
        formatted[numeric_cols] = formatted[numeric_cols].round(2)
    formatted = formatted.astype(object)
    formatted[formatted == 0] = 'n/a'
    return formatted.where(pd.notna(formatted), 'n/a')


def export_to_excel_by_category(data, categories, report_prefix, market_type, end_date):
    """将数据按分类导出为Excel文件，并设置单元格样式和颜色填充"""
    ordered_data = _ordered_data_by_categories(data, categories)
    wb = Workbook()
    wb.remove(wb.active)

    header_font_ch = Font(name='SimSun', size=11, bold=True)
    header_font_en = Font(name='New Times Roman', size=11, bold=True)
    data_font_ch = Font(name='SimSun', size=11)
    data_font_en = Font(name='New Times Roman', size=11)
    center_align = Alignment(horizontal="center")
    right_align = Alignment(horizontal="right")
    grey_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    include_market_region = should_include_market_region(market_type)
    market_cap_label = get_market_cap_column_label(market_type)

    used_sheet_titles: set[str] = set()

    for category, symbols in categories.items():
        category_data = {symbol: ordered_data[symbol] for symbol in symbols if symbol in ordered_data}
        if not category_data:
            continue

        sheet_title = _sanitize_sheet_title(category)
        original_title = sheet_title
        suffix = 1
        while sheet_title in used_sheet_titles:
            candidate = f"{original_title[:28]}_{suffix}"
            sheet_title = candidate[:31]
            suffix += 1
        used_sheet_titles.add(sheet_title)
        ws = wb.create_sheet(title=sheet_title)
        df = pd.DataFrame(category_data).T

        if include_market_region:
            df = df[['market_region', 'symbol', 'two_week_return', 'ytd_rate', 'mom_rate', 'yoy_rate',
                     'latest_close', 'market_cap', 'dividend_yield', 'sharp_ratio', 'annualized_volatility']]
            df.columns = ['市场区域', 'Symbol', '两周变动(%)', 'YTD(%)', 'MoM(%)', 'YoY(%)', '收盘',
                          market_cap_label, '股息率(%)', '夏普比率', '年化波动率']
        else:
            df = df[['symbol', 'two_week_return', 'ytd_rate', 'mom_rate', 'yoy_rate', 'latest_close',
                     'market_cap', 'dividend_yield', 'sharp_ratio', 'annualized_volatility']]
            df.columns = ['Symbol', '两周变动(%)', 'YTD(%)', 'MoM(%)', 'YoY(%)', '收盘',
                          market_cap_label, '股息率(%)', '夏普比率', '年化波动率']

        df = _format_report_frame(df)

        for col_idx, header in enumerate(df.columns.tolist(), start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font_en if header.isascii() else header_font_ch
            cell.alignment = center_align

        for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=False), start=2):
            for c_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                if isinstance(value, str):
                    cell.font = data_font_en if value.isascii() else data_font_ch
                else:
                    cell.font = data_font_ch
                if include_market_region:
                    cell.alignment = center_align if c_idx <= 2 else right_align
                else:
                    cell.alignment = center_align if c_idx == 1 else right_align
                if value == 'n/a' and df.columns[c_idx - 1] not in NO_FILL_HEADERS:
                    cell.fill = grey_fill

        apply_gradient_fill(
            ws,
            skip_rows=1,
            skip_columns=1 if include_market_region else 0,
            excluded_headers=NO_FILL_HEADERS,
        )

    ws_summary = wb.create_sheet(title="汇总", index=0)
    df_summary = pd.DataFrame(ordered_data).T

    if include_market_region:
        df_summary = df_summary[
            ['market_region', 'symbol', 'two_week_return', 'ytd_rate', 'mom_rate', 'yoy_rate',
             'latest_close', 'market_cap', 'dividend_yield', 'sharp_ratio', 'annualized_volatility']]
        df_summary.insert(0, 'category', [get_category_for_symbol(symbol, categories) for symbol in df_summary.index])
        df_summary.columns = ['分类', '市场区域', 'Symbol', '两周变动(%)', 'YTD(%)', 'MoM(%)', 'YoY(%)',
                              '收盘', market_cap_label, '股息率(%)', '夏普比率', '年化波动率']
        desired_headers = ['分类', '市场区域', 'Symbol', '收盘', '两周变动(%)', 'MoM(%)', 'YoY(%)', 'YTD(%)', '夏普比率', market_cap_label, '股息率(%)']
    else:
        df_summary = df_summary[
            ['symbol', 'two_week_return', 'ytd_rate', 'mom_rate', 'yoy_rate', 'latest_close',
             'market_cap', 'dividend_yield', 'sharp_ratio', 'annualized_volatility']]
        df_summary.insert(0, 'category', [get_category_for_symbol(symbol, categories) for symbol in df_summary.index])
        df_summary.columns = ['分类', 'Symbol', '两周变动(%)', 'YTD(%)', 'MoM(%)', 'YoY(%)', '收盘',
                              market_cap_label, '股息率(%)', '夏普比率', '年化波动率']
        desired_headers = ['分类', 'Symbol', '收盘', '两周变动(%)', 'MoM(%)', 'YoY(%)', 'YTD(%)', '夏普比率', market_cap_label, '股息率(%)']

    df_summary = _format_report_frame(df_summary)
    ordered_headers = [h for h in desired_headers if h in df_summary.columns]
    if ordered_headers:
        df_summary = df_summary[ordered_headers]

    for col_idx, header in enumerate(df_summary.columns.tolist(), start=1):
        cell = ws_summary.cell(row=1, column=col_idx, value=header)
        cell.font = header_font_en if header.isascii() else header_font_ch
        cell.alignment = center_align

    for r_idx, row in enumerate(dataframe_to_rows(df_summary, index=False, header=False), start=2):
        for c_idx, value in enumerate(row, start=1):
            cell = ws_summary.cell(row=r_idx, column=c_idx, value=value)
            if isinstance(value, str):
                cell.font = data_font_en if value.isascii() else data_font_ch
            else:
                cell.font = data_font_ch
            if include_market_region:
                cell.alignment = center_align if c_idx <= 3 else right_align
            else:
                cell.alignment = center_align if c_idx <= 2 else right_align
            if value == 'n/a' and df_summary.columns[c_idx - 1] not in NO_FILL_HEADERS:
                cell.fill = grey_fill

    apply_gradient_fill(
        ws_summary,
        skip_rows=1,
        skip_columns=2 if include_market_region else 1,
        excluded_headers=NO_FILL_HEADERS,
    )

    filename = APP_CONFIG.output_dir / f'{report_prefix}_{end_date.strftime("%Y%m%d")}.xlsx'
    wb.save(filename)
    print(f"{market_type}分类报告已保存为: {filename}")
    return filename


def main(
    market_mode: str | None = None,
    use_default_dates: bool | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    retry_attempts: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    cancel_check=None,
) -> Path | None:
    del progress_callback, cancel_check
    _refresh_runtime_config()
    market_mode = resolve_config_value(
        explicit=market_mode,
        env_key="AMR_SECONDARY_MARKET_MODE",
        default=CONFIG["market_mode"],
        caster=lambda raw: raw,
    )
    use_default_dates = resolve_config_value(
        explicit=use_default_dates,
        env_key="AMR_SECONDARY_USE_DEFAULT_DATES",
        default=CONFIG["use_default_dates"],
        caster=parse_bool,
    )
    start_date = resolve_config_value(
        explicit=start_date,
        env_key="AMR_SECONDARY_START_DATE",
        default=CONFIG["start_date"],
        caster=lambda raw: raw,
    )
    end_date = resolve_config_value(
        explicit=end_date,
        env_key="AMR_SECONDARY_END_DATE",
        default=CONFIG["end_date"],
        caster=lambda raw: raw,
    )
    retry_attempts = resolve_config_value(
        explicit=retry_attempts,
        env_key="AMR_SECONDARY_RETRY_ATTEMPTS",
        default=CONFIG["retry_attempts"],
        caster=lambda raw: _coerce_int(raw, CONFIG["retry_attempts"]),
    )
    max_workers = resolve_config_value(
        explicit=max_workers,
        env_key="AMR_SECONDARY_MAX_WORKERS",
        default=CONFIG["max_workers"],
        caster=lambda raw: _coerce_int(raw, CONFIG["max_workers"]),
    )
    CONFIG["retry_attempts"] = _coerce_int(retry_attempts, CONFIG["retry_attempts"])
    CONFIG["max_workers"] = max(1, _coerce_int(max_workers, CONFIG["max_workers"]))
    if market_mode is None and use_default_dates is None and start_date is None and end_date is None:
        _print_intro()
    market_symbols, categories, market_type, report_prefix = resolve_market_selection(market_mode)
    start_date, end_date = resolve_date_selection(
        use_default_dates=use_default_dates,
        start_date=start_date,
        end_date=end_date,
    )
    print(f"数据日期范围：{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"将分析以下 {len(market_symbols)} 个{market_type}标的：")

    # 按分类显示标的
    for category, symbols in categories.items():
        print(f"  {category}: {', '.join(symbols)}")

    # 下载数据
    weekly_data = get_weekly_data(market_symbols, start_date, end_date)

    print("正在计算指标...")
    results: dict[str, dict] = {}
    ordered_items = list(weekly_data.items())
    for name, df in ordered_items:
        try:
            results[name] = calculate_indicators(df, name, market_symbols, market_type, start_date, end_date)
        except Exception as e:
            print(f"计算 {name} 指标时出错: {e}")

    results = {name: results[name] for name, _df in ordered_items if name in results}

    # 导出Excel文件
    if results:
        output_path = export_to_excel_by_category(results, categories, report_prefix, market_type, end_date)
        print("数据处理完毕！")
        print(f"成功分析了 {len(results)} 个标的")

        # 显示各分类的标的数量
        for category, symbols in categories.items():
            count = sum(1 for symbol in symbols if symbol in results)
            print(f"  {category}: {count}/{len(symbols)} 个标的")
        return output_path
    else:
        print("没有获取到任何数据，请检查网络连接和符号列表。")
        return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行二级市场周报。")
    parser.add_argument("--market-mode", choices=["us", "china", "hk", "mixed"], help="指定市场模式。")
    parser.add_argument("--use-default-dates", action="store_true", default=None, help="使用默认两周区间。")
    parser.add_argument("--start-date", help="开始日期，格式 YYYY-MM-DD。")
    parser.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD。")
    parser.add_argument("--retry-attempts", type=int, help="失败标的的集中重试次数。")
    parser.add_argument("--max-workers", type=int, help="并发线程数。")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    main(
        market_mode=args.market_mode,
        use_default_dates=args.use_default_dates,
        start_date=args.start_date,
        end_date=args.end_date,
        retry_attempts=args.retry_attempts,
        max_workers=args.max_workers,
    )
