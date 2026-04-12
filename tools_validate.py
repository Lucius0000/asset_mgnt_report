from __future__ import annotations

from pathlib import Path

from src.asset_mgnt_report.services.validation import build_markdown_report, compare_excel_files


OUTPUT_FILES = [
    "cpi_metrics.xlsx",
    "gdp_metrics.xlsx",
    "interest_rate_metrics.xlsx",
    "fx_metrics.xlsx",
    "commodity_indicators_summary.xlsx",
    "crypto_metrics.xlsx",
    "bonds.xlsx",
    "stock_weekly_report.xlsx",
    "Gainer.xlsx",
    "mixed_market_report_20260104.xlsx",
    "整体_processed.xlsx",
]


def main() -> None:
    root = Path(__file__).resolve().parent
    main_output = root.parent / "main" / "output"
    codex_output = root / "output"
    results = [
        compare_excel_files(main_output / name, codex_output / name, tolerance=1e-4) for name in OUTPUT_FILES
    ]
    report_path = root / "docs" / "重构前后对比报告.md"
    build_markdown_report(
        results,
        report_path,
        title="重构前后对比报告",
        assumptions=[
            "main 与 codex 使用同一份种子数据与固定参数。",
            "数值字段容差设为 1e-4。",
            "若存在算法统一导致的差异，需要在报告中补充解释。",
        ],
    )
    for item in results:
        print(f"{item.file_name}: {item.status} - {item.detail}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
