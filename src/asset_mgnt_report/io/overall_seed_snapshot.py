from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.asset_mgnt_report.config.defaults import AppConfig, build_app_config

SNAPSHOT_FILE_NAME = "overall_seed_snapshot.json"


def get_snapshot_path(config: AppConfig | None = None) -> Path:
    app_config = config or build_app_config()
    return app_config.raw_output_dir / SNAPSHOT_FILE_NAME


def _default_snapshot() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "sheet1_assets": {},
        "sheet2_fx": {},
    }


def load_overall_seed_snapshot(config: AppConfig | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    snapshot_path = get_snapshot_path(config)
    if not snapshot_path.exists():
        return _default_snapshot()
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot = _default_snapshot()
    snapshot["sheet1_assets"].update(payload.get("sheet1_assets", {}))
    snapshot["sheet2_fx"].update(payload.get("sheet2_fx", {}))
    return snapshot


def save_overall_seed_snapshot(snapshot: dict[str, dict[str, dict[str, Any]]], config: AppConfig | None = None) -> Path:
    snapshot_path = get_snapshot_path(config)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return snapshot_path


def make_sheet1_asset_key(region: str, asset_class: str | None) -> str:
    clean_region = str(region).strip()
    clean_asset = str(asset_class).strip() if asset_class not in (None, "") else ""
    return clean_region if not clean_asset else f"{clean_region}|{clean_asset}"


def _normalize_json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize_json_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def upsert_sheet1_asset_metrics(
    *,
    region: str,
    asset_class: str | None,
    fields: dict[str, Any],
    config: AppConfig | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    snapshot = load_overall_seed_snapshot(config)
    key = make_sheet1_asset_key(region, asset_class)
    current = deepcopy(snapshot["sheet1_assets"].get(key, {}))
    current.update(
        {
            "区域": str(region).strip(),
            "资产大类": None if asset_class in (None, "") else str(asset_class).strip(),
        }
    )
    current.update(fields)
    current = _normalize_json_value(current)
    snapshot["sheet1_assets"][key] = current
    save_overall_seed_snapshot(snapshot, config)
    return snapshot


def get_sheet1_asset_metrics(
    region: str,
    asset_class: str | None,
    config: AppConfig | None = None,
) -> dict[str, Any] | None:
    snapshot = load_overall_seed_snapshot(config)
    return snapshot["sheet1_assets"].get(make_sheet1_asset_key(region, asset_class))


def upsert_sheet2_fx_rows(
    rows: list[dict[str, Any]],
    *,
    config: AppConfig | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    snapshot = load_overall_seed_snapshot(config)
    for row in rows:
        pair_name = str(row.get("货币汇率", "")).strip()
        if not pair_name:
            continue
        snapshot["sheet2_fx"][pair_name] = _normalize_json_value(deepcopy(row))
    save_overall_seed_snapshot(snapshot, config)
    return snapshot
