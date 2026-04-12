from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    data_dir: Path
    seed_data_dir: Path
    local_data_dir: Path
    output_dir: Path
    raw_output_dir: Path
    assets_dir: Path
    archive_dir: Path
    debug: bool = False
    use_proxy: bool = False
    http_proxy: str = "http://127.0.0.1:7890"
    https_proxy: str = "http://127.0.0.1:7890"
    fred_api_key: str | None = None
    risk_free_rates: dict[str, float] = field(
        default_factory=lambda: {"US": 0.045, "CN": 0.017, "HK": 0.0062}
    )

    def ensure_runtime_dirs(self) -> None:
        for path in (self.data_dir, self.seed_data_dir, self.local_data_dir, self.output_dir, self.raw_output_dir):
            path.mkdir(parents=True, exist_ok=True)


def build_app_config(project_root: str | Path | None = None, overrides: dict[str, Any] | None = None) -> AppConfig:
    root = Path(project_root or Path(__file__).resolve().parents[3]).resolve()
    config = AppConfig(
        project_root=root,
        data_dir=root / "data",
        seed_data_dir=root / "data" / "seeds",
        local_data_dir=root / "data" / "local",
        output_dir=root / "output",
        raw_output_dir=root / "output" / "raw_data",
        assets_dir=root / "docs" / "assets",
        archive_dir=root / "archive",
        debug=_env_bool("AMR_DEBUG", False),
        use_proxy=_env_bool("AMR_USE_PROXY", False),
        http_proxy=os.getenv("AMR_HTTP_PROXY", "http://127.0.0.1:7890"),
        https_proxy=os.getenv("AMR_HTTPS_PROXY", "http://127.0.0.1:7890"),
        fred_api_key=os.getenv("FRED_API_KEY"),
    )
    if overrides:
        for key, value in overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)
    config.ensure_runtime_dirs()
    if config.use_proxy:
        os.environ["http_proxy"] = config.http_proxy
        os.environ["https_proxy"] = config.https_proxy
    return config
