from __future__ import annotations

import argparse
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_targets(root: Path) -> list[Path]:
    return [root / "scripts"]


def newline_stats(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    return crlf, lf, cr


def has_mixed_newlines(path: Path) -> bool:
    crlf, lf, cr = newline_stats(path)
    return sum(value > 0 for value in (crlf, lf, cr)) > 1 or cr > 0


def normalize_to_lf(path: Path) -> None:
    content = path.read_text(encoding="utf-8", errors="ignore")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(content, encoding="utf-8", newline="\n")


def iter_python_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            files.append(target)
            continue
        if not target.exists():
            continue
        files.extend(sorted(path for path in target.rglob("*.py") if "__pycache__" not in path.parts))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan or normalize mixed line endings in Python scripts.")
    parser.add_argument("targets", nargs="*", help="Files or directories to scan. Defaults to the repo scripts directory.")
    parser.add_argument("--write", action="store_true", help="Normalize mixed line endings to LF in-place.")
    parser.add_argument("--quiet", action="store_true", help="Only print files that need changes.")
    args = parser.parse_args()

    root = project_root()
    targets = [Path(target).resolve() for target in args.targets] if args.targets else default_targets(root)
    python_files = iter_python_files(targets)

    mixed_files: list[Path] = []
    for path in python_files:
        if not has_mixed_newlines(path):
            continue
        mixed_files.append(path)
        if args.write:
            normalize_to_lf(path)
        if not args.quiet:
            crlf, lf, cr = newline_stats(path)
            print(f"{path} | CRLF={crlf} LF={lf} CR={cr}")

    if args.write:
        print(f"normalized={len(mixed_files)}")
    else:
        print(f"mixed={len(mixed_files)}")

    return 1 if mixed_files and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
