from __future__ import annotations

from src.asset_mgnt_report.config.defaults import build_app_config


def get_risk_free_rate(region_code: str) -> float:
    config = build_app_config()
    return config.risk_free_rates[region_code]
