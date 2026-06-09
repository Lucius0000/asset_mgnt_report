from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import overall
from scripts.pipelines import crypto_report, fx_report, secondary_market_report, stock_cap_report, stock_index_report
from src.asset_mgnt_report.io import overall_seed_snapshot


def test_overall_paths_resolve_to_project_root() -> None:
    assert overall.CONFIG["input_path"] == overall.APP_CONFIG.seed_data_dir / "整体.xlsx"
    assert overall.CONFIG["output_path"] == overall.APP_CONFIG.output_dir / "整体_processed.xlsx"
    assert overall.CONFIG["log_path"] == overall.APP_CONFIG.raw_output_dir / "整体_calculation_steps.txt"
    assert overall_seed_snapshot.get_snapshot_path(overall.APP_CONFIG) == overall.APP_CONFIG.raw_output_dir / "overall_seed_snapshot.json"


def test_stock_cap_paths_resolve_to_project_root() -> None:
    assert stock_cap_report.SEED_DATA_DIR == stock_cap_report.APP_CONFIG.seed_data_dir
    assert stock_cap_report.RAW_OUTPUT_DIR == stock_cap_report.APP_CONFIG.raw_output_dir
    assert stock_cap_report.SEED_DATA_DIR.name == "seeds"
    assert stock_cap_report.RAW_OUTPUT_DIR.name == "raw_data"


def test_main_pipeline_outputs_resolve_to_project_root() -> None:
    assert stock_index_report.APP_CONFIG.output_dir == stock_index_report.PROJECT_ROOT / "output"
    assert stock_index_report.APP_CONFIG.raw_output_dir == stock_index_report.PROJECT_ROOT / "output" / "raw_data"
    assert fx_report.RAW_DATA_DIR == fx_report.APP_CONFIG.raw_output_dir
    assert isinstance(fx_report.RAW_DATA_DIR, Path)
    assert Path(crypto_report.OUTPUT_DIR) == crypto_report.APP_CONFIG.output_dir


def test_secondary_market_exports_resolve_to_project_root(monkeypatch) -> None:
    saved_paths: list[Path] = []

    def fake_save(_self, filename):
        saved_paths.append(Path(filename))

    monkeypatch.setattr(secondary_market_report.Workbook, "save", fake_save)
    secondary_market_report.export_to_excel_by_category(
        data={
            "SPY": {
                "symbol": "SPY",
                "two_week_return": 1.2,
                "ytd_rate": 3.4,
                "mom_rate": 0.5,
                "yoy_rate": 7.8,
                "latest_close": 500.0,
                "market_cap": 1000.0,
                "dividend_yield": 1.2,
                "sharp_ratio": 0.8,
                "annualized_volatility": 15.0,
            }
        },
        categories={"股票-大盘": ["SPY"]},
        report_prefix="us_market_report",
        market_type="美股",
        end_date=secondary_market_report.datetime(2026, 4, 18),
    )
    assert saved_paths
    assert saved_paths[0].parent == secondary_market_report.APP_CONFIG.output_dir


def test_secondary_market_summary_respects_category_order(monkeypatch) -> None:
    saved_workbooks = []

    def fake_save(self, _filename):
        saved_workbooks.append(self)

    def metrics(symbol: str, market_region: str) -> dict:
        return {
            "market_region": market_region,
            "symbol": symbol,
            "two_week_return": 1.0,
            "ytd_rate": 2.0,
            "mom_rate": 3.0,
            "yoy_rate": 4.0,
            "latest_close": 10.0,
            "market_cap": 100.0,
            "dividend_yield": 1.5,
            "sharp_ratio": 0.8,
            "annualized_volatility": 12.0,
        }

    categories = {
        "大盘": ["SPY"],
        "中国A股-Smart Beta-中盘": ["南方中证500ETF"],
        "港股-Smart Beta-红利": ["平安香港高息ETF"],
    }

    monkeypatch.setattr(secondary_market_report.Workbook, "save", fake_save)
    secondary_market_report.export_to_excel_by_category(
        data={
            "平安香港高息ETF": metrics("3070.HK", "港股"),
            "南方中证500ETF": metrics("510500.SS", "中国A股"),
            "SPY": metrics("SPY", "美股"),
        },
        categories=categories,
        report_prefix="mixed_market_report",
        market_type="混合",
        end_date=secondary_market_report.datetime(2026, 4, 18),
    )

    assert saved_workbooks
    wb = saved_workbooks[0]
    assert wb.sheetnames[:4] == ["汇总", "大盘", "中国A股_Smart Beta_中盘", "港股_Smart Beta_红利"]
    summary_categories = [wb["汇总"].cell(row=row, column=1).value for row in range(2, 5)]
    assert summary_categories == list(categories)


def test_secondary_market_supports_split_china_and_hk_modes() -> None:
    china_symbols, china_categories, china_market_type, china_prefix = secondary_market_report.resolve_market_selection("china")
    assert china_market_type == "中国A股"
    assert china_prefix == "china_market_report"
    assert "华泰柏瑞沪深300ETF" in china_symbols
    assert china_symbols["中证红利"] == "515180.SS"
    assert "易方达蓝筹精选" not in china_symbols
    assert "恒生指数盈富基金" not in china_symbols
    assert "个股-消费" in china_categories
    assert "Smart Beta-红利低波" in china_categories
    assert "南方中证500ETF" not in china_categories["大盘"]
    assert china_categories["Smart Beta-中盘"] == ["南方中证500ETF"]
    assert china_categories["Smart Beta-小盘"] == ["南方中证1000ETF"]
    assert list(china_categories).index("Smart Beta-中盘") == list(china_categories).index("个股-金属") + 1
    assert list(china_categories).index("Smart Beta-小盘") == list(china_categories).index("Smart Beta-中盘") + 1

    hk_symbols, hk_categories, hk_market_type, hk_prefix = secondary_market_report.resolve_market_selection("hk")
    assert hk_market_type == "港股"
    assert hk_prefix == "hk_market_report"
    assert "恒生指数盈富基金" in hk_symbols
    assert hk_symbols["平安香港高息ETF"] == "3070.HK"
    assert hk_symbols["恒生高息股30ETF"] == "3466.HK"
    assert "华泰柏瑞沪深300ETF" not in hk_symbols
    assert "大盘" in hk_categories
    assert hk_categories["Smart Beta-红利"] == ["平安香港高息ETF", "恒生高息股30ETF"]
    assert "个股-互联网" in hk_categories
    assert list(hk_categories)[-1] == "Smart Beta-红利"


def test_secondary_market_sheet_title_sanitizes_invalid_characters() -> None:
    assert secondary_market_report._sanitize_sheet_title("个股-半导体/算力") == "个股_半导体_算力"


def test_secondary_market_normalizes_single_ticker_multiindex_columns() -> None:
    frame = pd.DataFrame(
        [[10.0, 11.0], [12.0, 13.0]],
        columns=pd.MultiIndex.from_tuples(
            [("Close", "SPY"), ("Open", "SPY")],
            names=["Price", "Ticker"],
        ),
        index=pd.to_datetime(["2026-05-21", "2026-05-22"]),
    )
    normalized = secondary_market_report._normalize_history_frame(frame)

    assert list(normalized.columns) == ["Close", "Open"]
    assert secondary_market_report._get_latest_close_from_history(normalized) == 12.0


def test_secondary_market_format_report_frame_has_no_deprecated_warnings(recwarn) -> None:
    frame = pd.DataFrame({"收盘": [10.126, 0.0, None], "Symbol": ["A", "B", "C"]})
    formatted = secondary_market_report._format_report_frame(frame)

    assert formatted["收盘"].tolist() == [10.13, "n/a", "n/a"]
    assert not recwarn.list


def test_secondary_market_does_not_color_close_column() -> None:
    wb = secondary_market_report.Workbook()
    ws = wb.active
    ws.append(["Symbol", "收盘", "两周变动(%)"])
    ws.append(["A", 10.0, 1.0])
    ws.append(["B", 11.0, -1.0])

    secondary_market_report.apply_gradient_fill(
        ws,
        skip_rows=1,
        skip_columns=0,
        excluded_headers=secondary_market_report.NO_FILL_HEADERS,
    )

    assert ws["B2"].fill.fill_type is None
    assert ws["B3"].fill.fill_type is None
    assert ws["C2"].fill.fill_type == "solid"


def test_secondary_market_mixed_mode_keeps_market_category_order() -> None:
    mixed_symbols, mixed_categories, mixed_market_type, mixed_prefix = secondary_market_report.resolve_market_selection("mixed")
    assert mixed_market_type == "混合"
    assert mixed_prefix == "mixed_market_report"
    assert "中国平安" in mixed_symbols
    assert secondary_market_report.get_category_for_symbol("中国平安", mixed_categories) == "中国A股-个股-金融"
    assert secondary_market_report.get_category_for_symbol("宁德时代", mixed_categories) == "中国A股-个股-新能源"
    assert secondary_market_report.get_category_for_symbol("南方中证500ETF", mixed_categories) == "中国A股-Smart Beta-中盘"
    assert secondary_market_report.get_category_for_symbol("南方中证1000ETF", mixed_categories) == "中国A股-Smart Beta-小盘"
    assert secondary_market_report.get_category_for_symbol("平安香港高息ETF", mixed_categories) == "港股-Smart Beta-红利"
    assert "SPY" in mixed_categories["大盘"]
    assert "华泰柏瑞沪深300ETF" in mixed_categories["中国A股-大盘"]
    assert "南方中证500ETF" not in mixed_categories["中国A股-大盘"]
    assert "南方中证1000ETF" not in mixed_categories["中国A股-大盘"]
    assert "恒生指数盈富基金" in mixed_categories["港股-大盘"]

    category_order = list(mixed_categories)
    assert category_order.index("中国A股-Smart Beta-中盘") == category_order.index("中国A股-个股-金属") + 1
    assert category_order.index("中国A股-Smart Beta-小盘") == category_order.index("中国A股-Smart Beta-中盘") + 1
    assert category_order.index("港股-Smart Beta-红利") == len(category_order) - 1
