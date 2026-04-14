from __future__ import annotations

from pathlib import Path

from scripts import overall
from scripts.pipelines import fx_report, stock_cap_report, stock_index_report


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
