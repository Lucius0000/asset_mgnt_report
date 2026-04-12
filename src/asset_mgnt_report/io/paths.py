from __future__ import annotations

from pathlib import Path

from src.asset_mgnt_report.config.defaults import AppConfig, build_app_config


def get_app_config() -> AppConfig:
    return build_app_config()


def project_path(*parts: str) -> Path:
    return get_app_config().project_root.joinpath(*parts)
