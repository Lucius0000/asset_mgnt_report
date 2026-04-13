from __future__ import annotations

from typing import Any, Callable


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class JobCancelledError(RuntimeError):
    """Raised when a cooperative background job receives a cancel request."""


def emit_progress(progress_callback: ProgressCallback | None, event_type: str, **payload: Any) -> None:
    if progress_callback is None:
        return
    event = {"event": event_type, **payload}
    progress_callback(event)


def ensure_not_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise JobCancelledError("任务已被取消。")
