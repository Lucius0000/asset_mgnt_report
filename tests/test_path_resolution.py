from __future__ import annotations

from pathlib import Path

from scripts import overall
from scripts.pipelines import crypto_report, fx_report, secondary_market_report, stock_cap_report, stock_index_report


def test_overall_paths_resolve_to_project_root() -> None:
    assert overall.CONFIG["input_path"] == overall.APP_CONFIG.seed_data_dir / "整体.xlsx"
    assert overall.CONFIG["output_path"] == overall.APP_CONFIG.output_dir / "整体_processed.xlsx"
    assert overall.CONFIG["log_path"] == overall.APP_CONFIG.raw_output_dir / "整体_calculation_steps.txt"


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
