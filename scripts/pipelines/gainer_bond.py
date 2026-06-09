"""Compute China and US bond market capitalization differences across two weeks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import os
import sys

import akshare as ak
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.asset_mgnt_report.config.inputs import resolve_config_value

DATA_DIR = PROJECT_ROOT / "data" / "seeds"

# 顶部配置区（适合 Spyder 直接运行）
# - target_date: 字符串或 datetime，格式 YYYY-MM-DD，例如 2026-03-27；若不是周五会自动归一化
CONFIG = {
    "target_date": None,
}


def _prompt_date(prompt: str, explicit: str | datetime | None = None) -> datetime:
    configured = resolve_config_value(
        explicit=explicit if explicit is not None else CONFIG["target_date"],
        env_key="AMR_BOND_TARGET_DATE",
        caster=lambda raw: datetime.strptime(raw, "%Y-%m-%d"),
    )
    if isinstance(configured, datetime):
        return configured
    if configured is not None:
        return datetime.strptime(str(configured), "%Y-%m-%d") if not isinstance(configured, datetime) else configured
    while True:
        raw = input(prompt).strip()
        if not raw:
            print("请输入日期（格式 YYYY-MM-DD），例如 2025-09-26。")
            continue
        try:
            target = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            print("日期格式无效，请重新输入。")
            continue
        return target


def _nearest_friday(d: datetime) -> datetime:
    # 已是周五（weekday=4）直接返回
    if d.weekday() == 4:
        return d
    # 最近的上/下一个周五；等距时取上一个周五
    days_back = (d.weekday() - 4) % 7
    last_friday = d - timedelta(days=days_back)
    days_forward = (4 - d.weekday()) % 7
    next_friday = d + timedelta(days=days_forward if days_forward != 0 else 7)
    return last_friday if (d - last_friday) <= (next_friday - d) else next_friday


def _previous_friday(target: datetime) -> datetime:
    candidate = target - timedelta(days=14)
    offset = (candidate.weekday() - 4) % 7
    return candidate - timedelta(days=offset)


def _extract_cn_treasury_value(date_obj: datetime) -> float:
    # 若传入日期不是周五，自动归一化到最近周五并提示
    normalized_date = _nearest_friday(date_obj)
    if normalized_date.date() != date_obj.date():
        print(f"提示：传入日期 {date_obj:%Y-%m-%d} 不是周五，已自动调整为距离最近的周五 {normalized_date:%Y-%m-%d}。")

    yyyymmdd = normalized_date.strftime("%Y%m%d")
    df = ak.bond_cash_summary_sse(date=yyyymmdd)
    if df.empty:
        raise RuntimeError(f"未能获取 {yyyymmdd} 的上交所债券托管数据。")
    label_col = "债券现货" if "债券现货" in df.columns else df.columns[0]
    value_col = "托管市值" if "托管市值" in df.columns else "托管面值"
    treasury = df[df[label_col].astype(str).str.contains("国债", na=False)]
    if treasury.empty:
        raise RuntimeError("返回数据中未找到‘国债’行。")
    raw_value = treasury.iloc[0][value_col]
    value = float(str(raw_value).replace(",", ""))
    return value / 10.0  # 亿元 -> 十亿 CNY


def _format_billion(value: float, currency: str, decimals: int) -> str:
    return f"{value:,.{decimals}f} B {currency}"


@dataclass
class UsbondsResult:
    latest_date: datetime
    previous_date: datetime
    latest_value: float
    previous_value: float


def _load_us_treasury_values() -> UsbondsResult:
    files = sorted(DATA_DIR.glob("MSPD_SumSecty*.csv"))
    if not files:
        raise RuntimeError(f"未找到 {DATA_DIR}\\MSPD_SumSecty*.csv。")
    csv_path = max(files, key=lambda p: p.stat().st_mtime)
    df = pd.read_csv(csv_path)
    if df.empty:
        raise RuntimeError(f"文件 {csv_path.name} 中没有数据。")
    df = df[df["Security Type Description"].astype(str).str.strip() == "Total Marketable"].copy()
    if df.empty:
        raise RuntimeError("CSV 中未找到 Security Type Description 为 Total Marketable 的记录。")
    df["Record Date"] = pd.to_datetime(df["Record Date"], errors="coerce")
    df = df.dropna(subset=["Record Date"]).sort_values("Record Date")
    if len(df) < 2:
        raise RuntimeError("Total Marketable 记录少于两条，无法计算差值。")
    latest = df.iloc[-1]
    previous = df.iloc[-2]

    def _to_float(value: object) -> float:
        return float(str(value).replace(",", ""))

    latest_val = _to_float(latest["Total Public Debt Outstanding (in Millions)"]) / 1000.0
    previous_val = _to_float(previous["Total Public Debt Outstanding (in Millions)"]) / 1000.0
    return UsbondsResult(
        latest_date=latest["Record Date"].to_pydatetime(),
        previous_date=previous["Record Date"].to_pydatetime(),
        latest_value=latest_val,
        previous_value=previous_val,
    )


def main(target_date: str | datetime | None = None) -> None:
    print("计算中美债券市场总市值差值\n")
    target_dt = _prompt_date("请输入收盘日期，需要最近的周五（YYYY-MM-DD）：", explicit=target_date)
    prev_date = _previous_friday(target_dt)

    try:
        cn_current = _extract_cn_treasury_value(target_dt)
        cn_previous = _extract_cn_treasury_value(prev_date)
    except Exception as exc:
        print(f"中国数据获取失败：{exc}")
    else:
        diff_cn = cn_current - cn_previous
        print("中国国债托管市值：")
        print(f"  {target_dt:%Y-%m-%d}: {_format_billion(cn_current, 'CNY', 2)}")
        print(f"  {prev_date:%Y-%m-%d}: {_format_billion(cn_previous, 'CNY', 2)}")
        print(f"  差值（当前 - 前两周）：{_format_billion(diff_cn, 'CNY', 2)}\n")

    try:
        us_result = _load_us_treasury_values()
    except Exception as exc:
        print(f"美国数据处理失败：{exc}")
    else:
        diff_us = us_result.latest_value - us_result.previous_value
        print("美国国债托管市值：")
        print(f"  {us_result.latest_date:%Y-%m-%d}: {_format_billion(us_result.latest_value, 'USD', 0)}")
        print(f"  {us_result.previous_date:%Y-%m-%d}: {_format_billion(us_result.previous_value, 'USD', 0)}")
        print(f"  差值（最新 - 次新）：{_format_billion(diff_us, 'USD', 0)}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="计算中美债券市值 Gainer。")
    parser.add_argument("--target-date", help="目标日期，格式 YYYY-MM-DD。若非周五会自动归一化。")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    main(target_date=args.target_date)
