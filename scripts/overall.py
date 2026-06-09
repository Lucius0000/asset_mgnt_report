"""
"周报-资产大类表现-整体" 表格计算。
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openpyxl import load_workbook

from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.io.overall_seed_snapshot import (
    load_overall_seed_snapshot,
    make_sheet1_asset_key,
)
from src.asset_mgnt_report.metrics.sharpe import adjusted_sharpe_ratio, sharpe_ratio

APP_CONFIG = build_app_config(project_root=PROJECT_ROOT)

# 顶部配置区（适合 Spyder 直接运行）
# - input_path / output_path / log_path: 路径对象或字符串；相对路径默认相对项目根目录
CONFIG = {
    "input_path": APP_CONFIG.seed_data_dir / "整体.xlsx",
    "output_path": APP_CONFIG.output_dir / "整体_processed.xlsx",
    "log_path": APP_CONFIG.raw_output_dir / "整体_calculation_steps.txt",
}


def read_percent_as_fraction(cell):
    v = cell.value
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().replace("％", "%")
        if s.endswith("%"):
            s = s[:-1]
        return float(s) / 100.0
    fmt = (cell.number_format or "").lower()
    return float(v) if "%" in fmt else float(v) / 100.0


def find_yoy(sheet, pair_name):
    header = [sheet.cell(1, c).value for c in range(1, sheet.max_column + 1)]
    yoy_cols = [i for i, v in enumerate(header, start=1) if v and "yoy" in str(v).lower()]
    for r in range(2, sheet.max_row + 1):
        row_has_pair = any(sheet.cell(r, c).value == pair_name for c in range(1, sheet.max_column + 1))
        if not row_has_pair:
            continue
        for yc in yoy_cols:
            val = sheet.cell(r, yc).value
            if val is not None:
                return float(val) / 100.0
    return None


def fmt_frac(x, d=6):
    return "None" if x is None else f"{x:.{d}f}"


def fmt_pctnum(x, d=2):
    if x is None:
        return "None"
    return f"{x * 100:.{d}f}"


def _header_map(sheet) -> dict[str, int]:
    return {
        str(sheet.cell(1, column).value).strip(): column
        for column in range(1, sheet.max_column + 1)
        if sheet.cell(1, column).value not in (None, "")
    }


def _sync_sheet1_from_snapshot(ws, log) -> None:
    headers = _header_map(ws)
    managed_columns = [
        "月收益率年化 (%)",
        "年收益率 (%)",
        "月波动率年化（%）",
        "总市值 ($)",
        "Gainer",
    ]
    missing_headers = [name for name in ["区域", "资产大类", *managed_columns] if name not in headers]
    if missing_headers:
        raise RuntimeError(f"Sheet1 缺少必要列：{', '.join(missing_headers)}")
    percent_columns = {"月收益率年化 (%)", "年收益率 (%)", "月波动率年化（%）"}

    snapshot = load_overall_seed_snapshot(APP_CONFIG)
    managed_keys = {
        make_sheet1_asset_key("美国", "股票权益"),
        make_sheet1_asset_key("美国", "债券固收"),
        make_sheet1_asset_key("中国", "股票权益"),
        make_sheet1_asset_key("中国", "债券固收"),
        make_sheet1_asset_key("香港", "股票权益"),
        make_sheet1_asset_key("商品与贵金属（黄金）", None),
        make_sheet1_asset_key("数字货币（BTC）", None),
    }

    current_region = None
    missing: list[str] = []
    for row_idx in range(2, ws.max_row + 1):
        region_cell_val = ws.cell(row_idx, headers["区域"]).value
        if region_cell_val not in (None, ""):
            current_region = str(region_cell_val).strip()
        asset_cell_val = ws.cell(row_idx, headers["资产大类"]).value
        asset_name = None if asset_cell_val in (None, "") else str(asset_cell_val).strip()
        region_name = current_region
        if not region_name:
            continue
        snapshot_key = make_sheet1_asset_key(region_name, asset_name)
        if snapshot_key not in managed_keys:
            continue
        snapshot_entry = snapshot["sheet1_assets"].get(snapshot_key)
        if snapshot_entry is None:
            missing.append(f"Sheet1 行 {row_idx} 缺少资产快照（{region_name} / {asset_name or '-'}）")
            continue
        for field_name in managed_columns:
            if field_name not in snapshot_entry:
                missing.append(f"Sheet1 行 {row_idx} 缺少字段 {field_name}（{region_name} / {asset_name or '-'}）")
                continue
            cell = ws.cell(row_idx, headers[field_name])
            cell.value = snapshot_entry[field_name]
            if field_name in percent_columns and isinstance(snapshot_entry[field_name], (int, float)):
                cell.number_format = "0.00%"
            log(
                f"[Seed Sync] Sheet1 row={row_idx} 区域={region_name} 资产={asset_name or '-'} "
                f"字段={field_name} 值={snapshot_entry[field_name]}"
            )
    if missing:
        raise RuntimeError("整体快照缺少必要字段：\n" + "\n".join(missing))


def _sync_sheet2_from_snapshot(ws2, log) -> None:
    headers = _header_map(ws2)
    required_columns = ["货币汇率", "汇率值", "日期", "MoM(%)", "YoY(%)", "5年均值", "5年均值周期"]
    missing_headers = [name for name in required_columns if name not in headers]
    if missing_headers:
        raise RuntimeError(f"Sheet2 缺少必要列：{', '.join(missing_headers)}")

    snapshot = load_overall_seed_snapshot(APP_CONFIG)
    fx_snapshot = snapshot["sheet2_fx"]
    required_pairs = ["USD_CNH", "USD_HKD", "CNH_HKD"]
    missing_rows: list[str] = []
    for pair_name in required_pairs:
        if pair_name not in fx_snapshot:
            missing_rows.append(f"Sheet2 缺少货币对 {pair_name}")
            continue
        row_payload = fx_snapshot[pair_name]
        for column_name in required_columns:
            if column_name not in row_payload:
                missing_rows.append(f"Sheet2 货币对 {pair_name} 缺少列 {column_name}")
    if missing_rows:
        raise RuntimeError("整体快照缺少必要汇率数据：\n" + "\n".join(missing_rows))

    if ws2.max_row > 1:
        ws2.delete_rows(2, ws2.max_row - 1)

    for pair_name in required_pairs:
        row_idx = ws2.max_row + 1
        row_payload = fx_snapshot[pair_name]
        for column_name in required_columns:
            ws2.cell(row_idx, headers[column_name]).value = row_payload[column_name]
        log(f"[Seed Sync] Sheet2 pair={pair_name} 已回填")


def main() -> None:
    input_path = CONFIG["input_path"]
    output_path = CONFIG["output_path"]
    log_path = CONFIG["log_path"]
    log_lines = []

    def log(message: str) -> None:
        print(message)
        log_lines.append(message)

    try:
        wb = load_workbook(input_path)
        ws = wb["Sheet1"]
        ws2 = wb["Sheet2"]

        log("=== Seed Sync Steps ===")
        _sync_sheet1_from_snapshot(ws, log)
        _sync_sheet2_from_snapshot(ws2, log)
        wb.save(input_path)
        log(f"[Seed Sync] 已覆盖写回整体种子文件：{input_path}")

        rf_by_region = {}
        current_region = None
        for r in range(2, ws.max_row + 1):
            region_cell_val = ws.cell(r, 1).value
            if region_cell_val not in (None, ""):
                current_region = str(region_cell_val).strip()
            asset = ws.cell(r, 2).value
            ret_frac = read_percent_as_fraction(ws.cell(r, 3))
            if asset == "债券固收" and current_region and ret_frac is not None:
                rf_by_region[current_region] = ret_frac

        us_rf = rf_by_region.get("美国", 0.0)
        cn_rf = rf_by_region.get("中国", None)
        hk_rf = 0.0062
        usd_cnh_yoy = find_yoy(ws2, "USD_CNH")
        usd_hkd_yoy = find_yoy(ws2, "USD_HKD")

        log("=== Calculation Steps ===")
        current_region = None
        for r in range(2, ws.max_row + 1):
            region_cell_val = ws.cell(r, 1).value
            if region_cell_val not in (None, ""):
                current_region = str(region_cell_val).strip()
            region = current_region
            asset = ws.cell(r, 2).value
            ret = read_percent_as_fraction(ws.cell(r, 3))
            vol = read_percent_as_fraction(ws.cell(r, 5))
            if ret is None or vol is None:
                continue
            if asset == "债券固收":
                ws.cell(r, 7).value = 0.00
                ws.cell(r, 8).value = 0.00
                continue

            rf_local = {"美国": us_rf, "中国": cn_rf, "香港": hk_rf}.get(region, us_rf)
            if rf_local is None:
                rf_local = us_rf
            sharpe = sharpe_ratio(ret, vol, rf_local)

            currency_effect = 0.0
            if region == "中国" and usd_cnh_yoy is not None:
                currency_effect = -usd_cnh_yoy
            elif region == "香港" and usd_hkd_yoy is not None:
                currency_effect = -usd_hkd_yoy
            adj_sharpe = adjusted_sharpe_ratio(ret, vol, us_rf, currency_effect)
            if asset in ("商品与贵金属（黄金）", "数字货币（BTC）"):
                adj_sharpe = sharpe

            log(
                f"[Row {r}] region={region} asset={asset} return={fmt_pctnum(ret)} "
                f"vol={fmt_pctnum(vol)} sharpe={fmt_frac(sharpe)} adjusted={fmt_frac(adj_sharpe)}"
            )
            ws.cell(r, 7).value = round(sharpe, 2)
            ws.cell(r, 7).number_format = "0.00"
            ws.cell(r, 8).value = round(adj_sharpe, 2)
            ws.cell(r, 8).number_format = "0.00"

        for r in range(2, ws.max_row + 1):
            for c in (3, 4, 5):
                cell = ws.cell(r, c)
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "0.00%"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)
    except Exception as exc:
        log(f"[Error] {exc}")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines), encoding="utf-8")
        raise

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
