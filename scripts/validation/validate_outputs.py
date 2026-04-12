from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
    project_root = PROJECT_ROOT
    sibling_main_output = project_root.parent / "main" / "output"
    container_main_output = Path("/baseline_main/output")
    main_output = sibling_main_output if sibling_main_output.exists() else container_main_output
    codex_output = project_root / "output"
    if not main_output.exists():
        raise FileNotFoundError(
            "未找到 main 基线输出目录。请在宿主机保留 ../main worktree，或在 Docker 中挂载 /baseline_main。"
        )
    results = [
        compare_excel_files(main_output / name, codex_output / name, tolerance=1e-4) for name in OUTPUT_FILES
    ]
    report_path = project_root / "docs" / "重构前后对比报告.md"
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
