from __future__ import annotations

import os
from typing import Callable, TypeVar

T = TypeVar("T")


def resolve_config_value(
    *,
    explicit: T | None = None,
    env_key: str | None = None,
    default: T | None = None,
    caster: Callable[[str], T] | None = None,
) -> T | None:
    if explicit is not None:
        return explicit
    if env_key:
        raw = os.getenv(env_key)
        if raw not in (None, ""):
            return caster(raw) if caster else raw  # type: ignore[return-value]
    return default


def parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_csv_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.replace("，", ",").split(",") if token.strip()]
