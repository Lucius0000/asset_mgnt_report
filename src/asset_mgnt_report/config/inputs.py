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
