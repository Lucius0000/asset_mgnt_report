from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(slots=True)
class ComparisonResult:
    file_name: str
    status: str
    detail: str


def compare_excel_files(main_file: Path, codex_file: Path, tolerance: float = 1e-6) -> ComparisonResult:
    if not main_file.exists():
        return ComparisonResult(main_file.name, "missing_main", "main branch output missing")
    if not codex_file.exists():
        return ComparisonResult(codex_file.name, "missing_codex", "codex branch output missing")

    main_sheets = pd.read_excel(main_file, sheet_name=None)
    codex_sheets = pd.read_excel(codex_file, sheet_name=None)
    if main_sheets.keys() != codex_sheets.keys():
        return ComparisonResult(main_file.name, "sheet_mismatch", "sheet names differ")

    differences: list[str] = []
    for sheet_name in main_sheets:
        left = main_sheets[sheet_name].fillna("")
        right = codex_sheets[sheet_name].fillna("")
        if left.shape != right.shape:
            differences.append(f"{sheet_name}: shape {left.shape} != {right.shape}")
            continue
        for column in left.columns:
            if column not in right.columns:
                differences.append(f"{sheet_name}: missing column {column}")
                continue
            if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(right[column]):
                delta = (left[column].astype(float) - right[column].astype(float)).abs().fillna(0)
                if not delta.le(tolerance).all():
                    differences.append(f"{sheet_name}: numeric diff in {column}")
            else:
                if not left[column].astype(str).equals(right[column].astype(str)):
                    differences.append(f"{sheet_name}: text diff in {column}")
    status = "match" if not differences else "diff"
    detail = "no differences" if not differences else "; ".join(differences[:10])
    return ComparisonResult(main_file.name, status, detail)


def build_markdown_report(
    results: Iterable[ComparisonResult],
    report_path: Path,
    *,
    title: str,
    assumptions: list[str],
) -> None:
    lines = [f"# {title}", "", "## 假设", ""]
    lines.extend([f"- {item}" for item in assumptions])
    lines.extend(["", "## 对比结果", ""])
    for item in results:
        lines.append(f"- `{item.file_name}`: {item.status} - {item.detail}")
    report_path.write_text("\n".join(lines), encoding="utf-8")
