"""
计算Gainer
对于美国市场债券，如果返回 0 B USD，可以根据 “MSPD_SumSecty_20241101_20251031.csv” 自行计算
选取隔月'Total Marketable'的 Total Public Debt Outstanding (in Millions)
= TEXT(F8/1000,"#,##") & " B USD"
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from scripts.pipelines import gainer_bond, gainer_btc, gainer_gold, gainer_stock
from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.config.inputs import parse_csv_list, resolve_config_value
from src.asset_mgnt_report.io.overall_seed_snapshot import upsert_sheet1_asset_metrics
from src.asset_mgnt_report.services.progress import emit_progress, ensure_not_cancelled

OUTPUT_PATH = PROJECT_ROOT / "output" / "Gainer.xlsx"
APP_CONFIG = build_app_config()

GAINER_MODULE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("stocks", "股票权益"),
    ("bonds", "债券固收"),
    ("gold", "商品与贵金属（黄金）"),
    ("btc", "数字货币（BTC）"),
)
GAINER_MODULE_LABELS = {key: label for key, label in GAINER_MODULE_OPTIONS}
STOCK_MARKET_OPTIONS: tuple[tuple[str, str], ...] = (
    ("CN", "中国"),
    ("US", "美国"),
    ("HK", "香港"),
)
STOCK_MARKET_LABELS = {key: label for key, label in STOCK_MARKET_OPTIONS}

# 顶部配置区（适合 Spyder 直接运行）
# - 支持的统一调度模块:
#   stocks -> scripts/pipelines/gainer_stock.py
#   bonds -> scripts/pipelines/gainer_bond.py
#   gold -> scripts/pipelines/gainer_gold.py
#   btc -> scripts/pipelines/gainer_btc.py
# - current_date / previous_date: 字符串或 datetime，格式 YYYY-MM-DD，例如 2026-04-11；两者都应为周六
# - current_gold_price / previous_gold_price: 浮点数，单位 USD/oz，例如 3240.5；仅 gold 子链路使用
# - modules: 列表，候选值为 stocks/bonds/gold/btc
# - stock_markets: 列表，候选值为 CN/US/HK；仅 stocks 子链路使用
# - output_path: 路径对象或字符串；相对路径默认相对项目根目录
CONFIG = {
    "current_date": None,
    "previous_date": None,
    "current_gold_price": None,
    "previous_gold_price": None,
    "modules": None,
    "stock_markets": None,
    "output_path": OUTPUT_PATH,
}


def _coerce_date_like(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    raise TypeError(f"无法识别的日期类型: {type(value)!r}")


def default_current_saturday(reference: date | datetime | None = None) -> datetime:
    ref = reference or datetime.today()
    if isinstance(ref, datetime):
        base = ref.date()
    else:
        base = ref

    # 周一到周四默认回到上周六；周五到周日默认指向本周六。
    if base.weekday() < 4:
        target = base - timedelta(days=base.weekday() + 2)
    else:
        target = base + timedelta(days=5 - base.weekday())
    return datetime.combine(target, datetime.min.time())


def default_gainer_dates(reference: date | datetime | None = None) -> tuple[datetime, datetime]:
    current = default_current_saturday(reference)
    previous = current - timedelta(days=14)
    return current, previous


def _prompt_date(message: str, default: Optional[datetime] = None) -> datetime:
    config_key = "current_date" if "本周末" in message else "previous_date"
    env_key = "AMR_GAINER_CURRENT_DATE" if "本周末" in message else "AMR_GAINER_PREVIOUS_DATE"
    configured = resolve_config_value(
        explicit=CONFIG[config_key],
        env_key=env_key,
        default=None,
        caster=lambda raw: raw,
    )
    if configured is not None:
        return _coerce_date_like(configured)
    while True:
        raw = input(message).strip()
        if not raw and default is not None:
            return default
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            suffix = f"，默认值 {default:%Y-%m-%d}" if default else ""
            print(f"日期格式无效，请使用 YYYY-MM-DD{suffix}")


def _normalize_choice_list(
    raw_value: object,
    options: tuple[tuple[str, str], ...],
) -> list[str]:
    allowed = {key.upper(): key for key, _ in options}
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        tokens = [token.strip().upper() for token in raw_value.replace("，", ",").split(",")]
    else:
        tokens = [str(token).strip().upper() for token in raw_value]
    normalized = [allowed[token] for token in tokens if token in allowed]
    return [key for key, _ in options if key in normalized]


def _prompt_choice_list(
    *,
    prompt: str,
    default: list[str],
    options: tuple[tuple[str, str], ...],
    explicit: object,
    env_key: str,
) -> list[str]:
    configured = resolve_config_value(
        explicit=explicit,
        env_key=env_key,
        default=None,
        caster=lambda raw: raw,
    )
    if configured is not None:
        normalized = _normalize_choice_list(configured, options)
        if normalized:
            return normalized
        raise ValueError(f"{env_key} / CONFIG 的配置无效，请使用 {', '.join(key for key, _ in options)}。")

    option_hint = "、".join(f"{key}={label}" for key, label in options)
    default_hint = ",".join(default)
    while True:
        raw = input(f"{prompt}（可选：{option_hint}，回车默认 {default_hint}）：").strip()
        if not raw:
            return list(default)
        normalized = _normalize_choice_list(raw, options)
        if normalized:
            return normalized
        print(f"输入无效，请使用 {', '.join(key for key, _ in options)} 的逗号组合。")


def _ensure_saturday(date_value: datetime, label: str) -> None:
    if date_value.weekday() != 5:
        raise ValueError(f"{label} 必须是周六，当前为 {date_value:%Y-%m-%d}。")


def _format_billion(value: Optional[float], unit: str, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f} B {unit}"


def _to_billions(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value / 1_000_000_000


def _load_us_treasury_series() -> pd.DataFrame:
    files = sorted(gainer_bond.DATA_DIR.glob("MSPD_SumSecty*.csv"))
    if not files:
        raise FileNotFoundError(f"未找到 {gainer_bond.DATA_DIR}\\MSPD_SumSecty*.csv，请先更新美国国债数据。")
    csv_path = max(files, key=lambda p: p.stat().st_mtime)
    df = pd.read_csv(csv_path)
    if df.empty:
        raise RuntimeError(f"{csv_path.name} 没有数据。")
    df = df[df["Security Type Description"].astype(str).str.strip() == "Total Marketable"].copy()
    if df.empty:
        raise RuntimeError("CSV 中未找到 Security Type Description = Total Marketable 的记录。")
    df["Record Date"] = pd.to_datetime(df["Record Date"], errors="coerce")
    df = df.dropna(subset=["Record Date"]).sort_values("Record Date")
    df["Record Date"] = df["Record Date"].dt.normalize()

    def _to_float(value: object) -> float:
        return float(str(value).replace(",", ""))

    df["billions_usd"] = df["Total Public Debt Outstanding (in Millions)"].apply(_to_float) / 1000.0
    df = df[["Record Date", "billions_usd"]].drop_duplicates("Record Date", keep="last")
    return df


def _us_treasury_value_for(date_obj: datetime, series: pd.DataFrame) -> float:
    mask = series["Record Date"] <= date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    if not mask.any():
        raise ValueError(f"美国国债数据缺少 {date_obj:%Y-%m-%d} 及之前的记录。")
    return float(series.loc[mask].iloc[-1]["billions_usd"])


def _compute_bond_caps(current_date: datetime, previous_date: datetime) -> Dict[str, Dict[str, Optional[float]]]:
    results: Dict[str, Dict[str, Optional[float]]] = {
        "US": {"unit": "USD", "current": None, "previous": None},
        "CN": {"unit": "CNY", "current": None, "previous": None},
    }

    print("- 正在读取美国国债规模...")
    try:
        us_series = _load_us_treasury_series()
        results["US"]["current"] = _us_treasury_value_for(current_date, us_series)
        results["US"]["previous"] = _us_treasury_value_for(previous_date, us_series)
    except Exception as exc:
        print(f"  [警告] 美国国债数据获取失败：{exc}")

    print("- 正在读取中国国债规模...")
    try:
        results["CN"]["current"] = gainer_bond._extract_cn_treasury_value(current_date)
        results["CN"]["previous"] = gainer_bond._extract_cn_treasury_value(previous_date)
    except Exception as exc:
        print(f"  [警告] 中国国债数据获取失败：{exc}")

    return results


def _compute_stock_caps(
    date_old: str,
    date_new: str,
    selected_markets: list[str],
    progress_callback=None,
    cancel_check=None,
) -> Dict[str, Dict[str, Optional[float]]]:
    market_definitions: Dict[str, Dict[str, object]] = {
        "US": {
            "unit": "USD",
            "name": "S&P 500",
            "loader": gainer_stock.get_sp500_symbols,
        },
        "CN": {
            "unit": "CNY",
            "name": "HS300",
            "loader": gainer_stock.get_hs300_symbols,
        },
        "HK": {
            "unit": "HKD",
            "name": "HSI",
            "loader": gainer_stock.get_hsi_symbols_from_excel,
        },
    }
    results: Dict[str, Dict[str, Optional[float]]] = {}

    for market in selected_markets:
        config = market_definitions[market]
        results[market] = {
            "unit": str(config["unit"]),
            "name": str(config["name"]),
            "old": None,
            "new": None,
        }
        print(f"- 正在计算{config['name']}市值差异...")
        try:
            symbols = config["loader"]()
            old_val, new_val = gainer_stock.compute_index_caps(
                symbols,
                date_old,
                date_new,
                str(config["unit"]),
                str(config["name"]),
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            results[market]["old"], results[market]["new"] = old_val, new_val
        except Exception as exc:
            print(f"  [警告] {config['name']}市值计算失败：{exc}")

    return results


def _compute_btc_caps(previous_date: datetime, current_date: datetime) -> Tuple[Optional[float], Optional[float]]:
    print("- 正在收集 BTC 市值差异...")
    try:
        caps = gainer_btc._fetch_btc_market_caps_utc(previous_date.date(), current_date.date())
        old_val = gainer_btc._pick_cap_for_date(caps, previous_date.date())
        new_val = gainer_btc._pick_cap_for_date(caps, current_date.date())
    except Exception as exc:
        print(f"  [警告] BTC 市值获取失败：{exc}")
        return None, None
    return float(old_val), float(new_val)


def _compute_gold_caps(previous_price: float, current_price: float) -> Tuple[float, float]:
    print("- 正在计算黄金市值差异...")
    prev_cap = gainer_gold._calc_total_market_cap(previous_price)
    curr_cap = gainer_gold._calc_total_market_cap(current_price)
    return prev_cap, curr_cap


def main(
    current_date: str | date | datetime | None = None,
    previous_date: str | date | datetime | None = None,
    current_gold_price: float | None = None,
    previous_gold_price: float | None = None,
    modules: list[str] | None = None,
    stock_markets: list[str] | None = None,
    output_path: str | Path | None = None,
    progress_callback=None,
    cancel_check=None,
) -> None:
    resolved_modules = resolve_config_value(
        explicit=modules,
        env_key="AMR_GAINER_MODULES",
        default=CONFIG["modules"],
        caster=parse_csv_list,
    )
    selected_modules = _normalize_choice_list(resolved_modules, GAINER_MODULE_OPTIONS) if resolved_modules is not None else []
    if not selected_modules:
        selected_modules = _prompt_choice_list(
            prompt="请输入要运行的 Gainer 子模块",
            default=[key for key, _ in GAINER_MODULE_OPTIONS],
            options=GAINER_MODULE_OPTIONS,
            explicit=CONFIG["modules"],
            env_key="AMR_GAINER_MODULES",
        )
    if not selected_modules:
        raise ValueError("至少需要选择一个 Gainer 子模块。")

    selected_stock_markets: list[str] = []
    if "stocks" in selected_modules:
        resolved_stock_markets = resolve_config_value(
            explicit=stock_markets,
            env_key="AMR_GAINER_STOCK_MARKETS",
            default=CONFIG["stock_markets"],
            caster=parse_csv_list,
        )
        selected_stock_markets = _normalize_choice_list(resolved_stock_markets, STOCK_MARKET_OPTIONS) if resolved_stock_markets is not None else []
        if not selected_stock_markets:
            selected_stock_markets = _prompt_choice_list(
                prompt="请输入股票子模块需要运行的市场",
                default=[key for key, _ in STOCK_MARKET_OPTIONS],
                options=STOCK_MARKET_OPTIONS,
                explicit=CONFIG["stock_markets"],
                env_key="AMR_GAINER_STOCK_MARKETS",
            )
        if not selected_stock_markets:
            raise ValueError("股票子模块至少需要选择一个市场。")

    default_current, default_previous = default_gainer_dates()
    resolved_current_date = resolve_config_value(
        explicit=current_date,
        env_key="AMR_GAINER_CURRENT_DATE",
        default=CONFIG["current_date"],
        caster=lambda raw: raw,
    )
    if resolved_current_date is not None:
        current_dt = _coerce_date_like(resolved_current_date)
    else:
        current_dt = _prompt_date(
            f"请输入本周末日期（YYYY-MM-DD，周六），回车默认 {default_current:%Y-%m-%d}:",
            default=default_current,
        )
    _ensure_saturday(current_dt, "本周末日期")
    explicit_previous = previous_date is not None or CONFIG["previous_date"] is not None or os.getenv("AMR_GAINER_PREVIOUS_DATE")
    if not explicit_previous:
        default_previous = current_dt - timedelta(days=14)
    resolved_previous_date = resolve_config_value(
        explicit=previous_date,
        env_key="AMR_GAINER_PREVIOUS_DATE",
        default=CONFIG["previous_date"],
        caster=lambda raw: raw,
    )
    if resolved_previous_date is not None:
        previous_dt = _coerce_date_like(resolved_previous_date)
    else:
        previous_dt = _prompt_date(
            f"请输入两周前周末日期（YYYY-MM-DD，周六，回车默认 {default_previous:%Y-%m-%d}）：",
            default=default_previous,
        )
    _ensure_saturday(previous_dt, "两周前日期")
    if (current_dt - previous_dt).days != 14:
        raise ValueError("两周前日期需要与本周末日期相差 14 天，且两者都必须是周六。")

    resolved_current_gold_price = resolve_config_value(
        explicit=current_gold_price,
        env_key="AMR_GOLD_CURRENT_PRICE",
        default=CONFIG["current_gold_price"],
        caster=float,
    )
    resolved_previous_gold_price = resolve_config_value(
        explicit=previous_gold_price,
        env_key="AMR_GOLD_PREVIOUS_PRICE",
        default=CONFIG["previous_gold_price"],
        caster=float,
    )
    if "gold" in selected_modules:
        print("\n请提供 LBMA Gold Price PM（USD/oz）")
        print("src: https://www.lbma.org.uk/cn/prices-and-data#/")
        resolved_current_gold_price = gainer_gold._prompt_price(
            "本周末价格：",
            env_key="AMR_GOLD_CURRENT_PRICE",
            configured=resolved_current_gold_price,
        )
        resolved_previous_gold_price = gainer_gold._prompt_price(
            "两周前周末价格：",
            env_key="AMR_GOLD_PREVIOUS_PRICE",
            configured=resolved_previous_gold_price,
        )
    
    date_old_str = previous_dt.strftime("%Y-%m-%d")
    date_new_str = current_dt.strftime("%Y-%m-%d")

    step_templates = {
        "stocks": "股票市值",
        "bonds": "债券市值",
        "gold": "黄金市值",
        "btc": "BTC 市值",
    }
    steps = [
        (f"step_{module_name}", f"步骤 {index} / {step_templates[module_name]}")
        for index, module_name in enumerate(selected_modules, start=1)
    ]
    emit_progress(progress_callback, "job_init", total_units=len(steps), pending_units=[label for _, label in steps])

    step_labels = [label for _, label in steps]
    completed_labels: list[str] = []
    stock_caps: Dict[str, Dict[str, Optional[float]]] = {}
    bond_caps: Dict[str, Dict[str, Optional[float]]] = {}
    gold_prev = gold_curr = None
    btc_prev = btc_curr = None

    for index, module_name in enumerate(selected_modules, start=1):
        ensure_not_cancelled(cancel_check)
        step_key, step_label = steps[index - 1]
        print(f"\n[{step_label}] 汇总{step_templates[module_name]}数据")
        emit_progress(
            progress_callback,
            "step_start",
            step_key=step_key,
            step_label=step_label,
            completed_units=completed_labels,
            pending_units=step_labels[index - 1 :],
            progress_ratio=(index - 1) / len(steps),
        )
        if module_name == "stocks":
            stock_caps = _compute_stock_caps(
                date_old_str,
                date_new_str,
                selected_stock_markets,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
        elif module_name == "bonds":
            bond_caps = _compute_bond_caps(current_dt, previous_dt)
        elif module_name == "gold":
            gold_prev, gold_curr = _compute_gold_caps(resolved_previous_gold_price, resolved_current_gold_price)
        elif module_name == "btc":
            btc_prev, btc_curr = _compute_btc_caps(previous_dt, current_dt)
        completed_labels.append(step_label)
        emit_progress(
            progress_callback,
            "step_complete",
            step_key=step_key,
            step_label=step_label,
            completed_units=completed_labels,
            pending_units=step_labels[index:],
            progress_ratio=index / len(steps),
        )

    rows: List[Dict[str, Optional[str]]] = []

    if "stocks" in selected_modules:
        stock_region_labels = {"US": "美国", "CN": "中国", "HK": "香港"}
        for market in selected_stock_markets:
            market_caps = stock_caps.get(market)
            if not market_caps:
                continue
            old_value = _to_billions(market_caps["old"])
            new_value = _to_billions(market_caps["new"])
            rows.append({
                "区域": stock_region_labels[market],
                "资产大类": "股票权益",
                "Market Cap Last 2 week": _format_billion(old_value, str(market_caps["unit"])),
                "Market Cap This week": _format_billion(new_value, str(market_caps["unit"])),
                "Gainer": _format_billion(
                    None if old_value is None or new_value is None else new_value - old_value,
                    str(market_caps["unit"]),
                ),
            })
            upsert_sheet1_asset_metrics(
                region=stock_region_labels[market],
                asset_class="股票权益",
                fields={"Gainer": rows[-1]["Gainer"]},
                config=APP_CONFIG,
            )

    if "bonds" in selected_modules:
        us_bond_prev = bond_caps["US"]["previous"]
        us_bond_curr = bond_caps["US"]["current"]
        us_bond_prev_b = us_bond_prev if us_bond_prev is None else float(us_bond_prev)
        us_bond_curr_b = us_bond_curr if us_bond_curr is None else float(us_bond_curr)
        rows.append({
            "区域": "美国",
            "资产大类": "债券固收",
            "Market Cap Last 2 week": _format_billion(us_bond_prev_b, "USD", decimals=0),
            "Market Cap This week": _format_billion(us_bond_curr_b, "USD", decimals=0),
            "Gainer": _format_billion(
                None if us_bond_prev_b is None or us_bond_curr_b is None else us_bond_curr_b - us_bond_prev_b,
                "USD",
                decimals=0,
            ),
        })
        upsert_sheet1_asset_metrics(
            region="美国",
            asset_class="债券固收",
            fields={"Gainer": rows[-1]["Gainer"]},
            config=APP_CONFIG,
        )

        cn_bond_prev = bond_caps["CN"]["previous"]
        cn_bond_curr = bond_caps["CN"]["current"]
        rows.append({
            "区域": "中国",
            "资产大类": "债券固收",
            "Market Cap Last 2 week": _format_billion(cn_bond_prev, "CNY"),
            "Market Cap This week": _format_billion(cn_bond_curr, "CNY"),
            "Gainer": _format_billion(
                None if cn_bond_prev is None or cn_bond_curr is None else cn_bond_curr - cn_bond_prev,
                "CNY",
            ),
        })
        upsert_sheet1_asset_metrics(
            region="中国",
            asset_class="债券固收",
            fields={"Gainer": rows[-1]["Gainer"]},
            config=APP_CONFIG,
        )

    if "gold" in selected_modules:
        gold_prev_b = _to_billions(gold_prev)
        gold_curr_b = _to_billions(gold_curr)
        rows.append({
            "区域": "商品与贵金属（黄金）",
            "资产大类": None,
            "Market Cap Last 2 week": _format_billion(gold_prev_b, "USD"),
            "Market Cap This week": _format_billion(gold_curr_b, "USD"),
            "Gainer": _format_billion(
                None if gold_prev_b is None or gold_curr_b is None else gold_curr_b - gold_prev_b,
                "USD",
            ),
        })
        upsert_sheet1_asset_metrics(
            region="商品与贵金属（黄金）",
            asset_class=None,
            fields={
                "Gainer": rows[-1]["Gainer"],
                "总市值 ($)": rows[-1]["Market Cap This week"],
            },
            config=APP_CONFIG,
        )

    if "btc" in selected_modules:
        btc_prev_b = _to_billions(btc_prev)
        btc_curr_b = _to_billions(btc_curr)
        rows.append({
            "区域": "数字货币（BTC）",
            "资产大类": None,
            "Market Cap Last 2 week": _format_billion(btc_prev_b, "USD"),
            "Market Cap This week": _format_billion(btc_curr_b, "USD"),
            "Gainer": _format_billion(
                None if btc_prev_b is None or btc_curr_b is None else btc_curr_b - btc_prev_b,
                "USD",
            ),
        })
        upsert_sheet1_asset_metrics(
            region="数字货币（BTC）",
            asset_class=None,
            fields={"Gainer": rows[-1]["Gainer"]},
            config=APP_CONFIG,
        )

    df = pd.DataFrame(rows, columns=["区域", "资产大类", "Market Cap Last 2 week", "Market Cap This week", "Gainer"])
    resolved_output = resolve_config_value(
        explicit=output_path,
        env_key="AMR_GAINER_OUTPUT_PATH",
        default=CONFIG["output_path"],
        caster=lambda raw: raw,
    )
    target_output = Path(resolved_output or OUTPUT_PATH)
    if not target_output.is_absolute():
        target_output = PROJECT_ROOT / target_output
    target_output.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(target_output, index=False)
    print(f"\n整合结果已保存至：{target_output}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gainer 统一入口。")
    parser.add_argument("--current-date", help="本周末日期，格式 YYYY-MM-DD，需为周六。")
    parser.add_argument("--previous-date", help="两周前日期，格式 YYYY-MM-DD，需为周六。")
    parser.add_argument("--current-gold-price", type=float, help="本周末黄金价格。")
    parser.add_argument("--previous-gold-price", type=float, help="两周前黄金价格。")
    parser.add_argument("--modules", nargs="+", choices=[key for key, _ in GAINER_MODULE_OPTIONS], help="指定 Gainer 子模块。")
    parser.add_argument("--stock-markets", nargs="+", choices=[key for key, _ in STOCK_MARKET_OPTIONS], help="指定股票子模块市场。")
    parser.add_argument("--output-path", help="输出文件路径。")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    main(
        current_date=args.current_date,
        previous_date=args.previous_date,
        current_gold_price=args.current_gold_price,
        previous_gold_price=args.previous_gold_price,
        modules=args.modules,
        stock_markets=args.stock_markets,
        output_path=args.output_path,
    )
