from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import date, timedelta
import io
import os
from pathlib import Path
from threading import Lock, Thread
import time
import traceback
from uuid import uuid4

import streamlit as st

from scripts import gainer as gainer_entry
from scripts import main as main_entry
from scripts import overall as overall_entry
from scripts.pipelines import secondary_market_report as secondary_market_entry
from scripts.validation import validate_outputs
from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.services.progress import JobCancelledError


MODULE_OPTIONS: list[tuple[str, str]] = [
    ("cpi", "CPI"),
    ("gdp", "GDP"),
    ("interest_rate", "利率"),
    ("carry_trade", "利差"),
    ("stock_index", "股票权益"),
    ("secondary_market", "二级市场"),
    ("currency", "汇率"),
    ("precious_metals", "商品与贵金属"),
    ("bonds", "债券固收"),
    ("crypto", "数字货币"),
]
MODULE_LABELS = {key: label for key, label in MODULE_OPTIONS}
STOCK_MARKET_OPTIONS: list[tuple[str, str]] = [
    ("CN", "中国"),
    ("US", "美国"),
    ("HK", "香港"),
]
STOCK_MARKET_LABELS = {key: label for key, label in STOCK_MARKET_OPTIONS}
GAINER_MODULE_OPTIONS = list(gainer_entry.GAINER_MODULE_OPTIONS)
GAINER_MODULE_LABELS = dict(gainer_entry.GAINER_MODULE_LABELS)
HOME_CARDS = [
    ("main", "主报表工作台", "按模块执行周报主链路，适合日常更新。"),
    ("gainer", "Gainer 工作台", "输入日期与金价，稳定生成跨资产 Gainer 汇总。"),
    ("secondary_market", "二级市场工作台", "单独运行中港股 / 美股 / 混合市场两周报表。"),
    ("overall", "整体表工作台", "处理整体.xlsx 并输出整体_processed.xlsx。"),
    ("validation", "校验工作台", "对 main / codex 输出做回归对比，更新对比报告。"),
]
WORKSPACE_LABELS = {
    "home": "主页",
    "main": "主报表",
    "gainer": "Gainer",
    "secondary_market": "二级市场",
    "overall": "整体表",
    "validation": "全量校验",
}
SECONDARY_MARKET_MODE_OPTIONS: list[tuple[str, str]] = [
    ("us", "美股"),
    ("china_hk", "中港股"),
    ("mixed", "混合"),
]
SECONDARY_MARKET_MODE_LABELS = {key: label for key, label in SECONDARY_MARKET_MODE_OPTIONS}
_JOB_LOCK = Lock()
_JOB_REGISTRY: dict[str, dict[str, object]] = {}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600&display=swap');

        :root {
            --amr-bg: #f6f1e8;
            --amr-paper: #fbf8f3;
            --amr-ink: #14213d;
            --amr-muted: #5f6b7a;
            --amr-line: rgba(20, 33, 61, 0.14);
            --amr-accent: #b7791f;
            --amr-accent-strong: #8b5e15;
            --amr-accent-soft: rgba(183, 121, 31, 0.12);
            --amr-success: #176b4d;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(183, 121, 31, 0.18), transparent 30%),
                linear-gradient(180deg, #f2eadf 0%, var(--amr-bg) 40%, #f7f4ef 100%);
        }

        [data-testid="stAppViewContainer"] > .main .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2rem;
            max-width: 1380px;
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            color: var(--amr-ink);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(20,33,61,0.96), rgba(20,33,61,0.88));
        }

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] * {
            color: #f2eee7 !important;
        }

        [data-testid="stSidebar"] code {
            color: #f9f5ee !important;
            background: rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            padding: 0.1rem 0.35rem;
        }

        .amr-hero {
            padding: 1.55rem 1.7rem 1.45rem;
            border: 1px solid var(--amr-line);
            background:
                linear-gradient(135deg, rgba(20, 33, 61, 0.96), rgba(20, 33, 61, 0.82)),
                linear-gradient(180deg, rgba(183, 121, 31, 0.18), transparent);
            color: #f8f4ec;
            border-radius: 28px;
            box-shadow: 0 24px 80px rgba(20, 33, 61, 0.16);
            margin-bottom: 0.95rem;
        }

        .amr-eyebrow {
            letter-spacing: 0.24em;
            text-transform: uppercase;
            font-size: 0.74rem;
            opacity: 0.72;
            margin-bottom: 0.8rem;
        }

        .amr-hero h1 {
            font-family: "IBM Plex Serif", Georgia, serif;
            font-size: clamp(1.9rem, 4vw, 2.95rem);
            line-height: 1.02;
            margin: 0 0 0.55rem 0;
        }

        .amr-hero p {
            max-width: 58rem;
            font-size: 0.95rem;
            line-height: 1.58;
            margin: 0;
            color: rgba(248, 244, 236, 0.82);
        }

        .amr-panel {
            padding: 1.05rem 1.15rem;
            border: 1px solid var(--amr-line);
            border-radius: 22px;
            background: rgba(251, 248, 243, 0.86);
            box-shadow: 0 16px 40px rgba(20, 33, 61, 0.08);
            backdrop-filter: blur(6px);
            min-height: 118px;
        }

        .amr-panel h3 {
            font-family: "IBM Plex Serif", Georgia, serif;
            margin: 0 0 0.45rem 0;
            font-size: 1.08rem;
        }

        .amr-panel p {
            margin: 0;
            color: var(--amr-muted);
            line-height: 1.55;
            font-size: 0.94rem;
        }

        .amr-section-label {
            margin: 1rem 0 0.55rem 0;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: var(--amr-accent-strong);
        }

        .amr-meta {
            border-top: 1px solid var(--amr-line);
            margin-top: 1.35rem;
            padding-top: 1rem;
            color: var(--amr-muted);
            font-size: 0.95rem;
        }

        .amr-result {
            padding: 1.05rem 1.15rem;
            border-radius: 20px;
            border: 1px solid var(--amr-line);
            background: rgba(255,255,255,0.72);
            margin-top: 0.85rem;
            animation: amrFadeUp 260ms ease;
        }

        .amr-result strong {
            color: var(--amr-ink);
        }

        .amr-workspace-head {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .amr-workspace-copy h2 {
            font-family: "IBM Plex Serif", Georgia, serif;
            margin: 0;
            font-size: 1.55rem;
        }

        .amr-workspace-copy p {
            margin: 0.45rem 0 0 0;
            color: var(--amr-muted);
            max-width: 42rem;
            line-height: 1.7;
        }

        .amr-inline-note {
            margin-top: 0.9rem;
            padding: 0.85rem 1rem;
            border-radius: 16px;
            background: rgba(183, 121, 31, 0.08);
            color: var(--amr-accent-strong);
            border: 1px solid rgba(183, 121, 31, 0.12);
        }

        @keyframes amrFadeUp {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        div[data-testid="stButton"] > button {
            border-radius: 999px;
            border: 1px solid rgba(20, 33, 61, 0.12);
            background: linear-gradient(180deg, #fcfaf6, #f1e8db);
            color: var(--amr-ink);
            font-weight: 600;
            min-height: 2.65rem;
            box-shadow: none;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }

        div[data-testid="stButton"] > button:hover {
            border-color: rgba(183, 121, 31, 0.4);
            box-shadow: 0 10px 22px rgba(183, 121, 31, 0.16);
            transform: translateY(-1px);
        }

        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, var(--amr-accent), var(--amr-accent-strong));
            color: #fff9ef;
            border: 0;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button {
            background: rgba(255, 248, 236, 0.94);
            color: var(--amr-ink) !important;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button * {
            color: var(--amr-ink) !important;
            fill: var(--amr-ink) !important;
        }

        [data-testid="stSidebar"] .stCaption {
            color: rgba(242, 238, 231, 0.82) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="radio"] > div,
        [data-testid="stSidebar"] [data-baseweb="checkbox"] > div {
            color: #f2eee7 !important;
        }

        [data-testid="stSidebar"] [data-baseweb="radio"] label,
        [data-testid="stSidebar"] [data-baseweb="checkbox"] label {
            color: #f2eee7 !important;
        }

        [data-testid="stCodeBlock"] {
            border-radius: 18px;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stDateInputField"] input,
        [data-testid="stMultiSelect"] span,
        [data-testid="stMultiSelect"] input {
            color: var(--amr-ink) !important;
            -webkit-text-fill-color: var(--amr-ink) !important;
        }

        [data-testid="stTextInput"] input::placeholder {
            color: #8b95a3 !important;
            -webkit-text-fill-color: #8b95a3 !important;
        }

        div[data-testid="stButton"][data-testkey^="workspace-"] > button,
        div[data-testid="stButton"][data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(180deg, var(--amr-accent), var(--amr-accent-strong));
            color: #fff9ef !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
def _normalize_workspace(workspace: str | None) -> str:
    if workspace in {"home", "main", "gainer", "secondary_market", "overall", "validation"}:
        return workspace
    return "home"


def _default_overall_paths(config) -> dict[str, str]:
    return {
        "overall_input_path_text": str(config.seed_data_dir / "整体.xlsx"),
        "overall_output_path_text": str(config.output_dir / "整体_processed.xlsx"),
        "overall_log_path_text": str(config.raw_output_dir / "整体_calculation_steps.txt"),
    }


def _current_week_saturday(reference: date | None = None) -> date:
    return gainer_entry.default_current_saturday(reference).date()


def _default_secondary_market_dates() -> tuple[date, date]:
    start_dt, end_dt = secondary_market_entry.get_default_dates()
    return start_dt.date(), end_dt.date()


def _ensure_state(config) -> None:
    overall_defaults = _default_overall_paths(config)
    default_current_date = _current_week_saturday()
    default_previous_date = default_current_date - timedelta(days=14)
    secondary_start_date, secondary_end_date = _default_secondary_market_dates()
    defaults = {
        "active_workspace": _normalize_workspace(os.getenv("AMR_ACTIVE_WORKSPACE")),
        "debug": config.debug,
        "use_proxy": config.use_proxy,
        "main_modules": [key for key, _ in MODULE_OPTIONS],
        "main_stock_markets": list(main_entry.CONFIG["stock_markets"]),
        "gainer_modules": [key for key, _ in GAINER_MODULE_OPTIONS],
        "gainer_stock_markets": [key for key, _ in STOCK_MARKET_OPTIONS],
        "gainer_current_date": default_current_date,
        "gainer_previous_date": default_previous_date,
        "gainer_current_gold_price": "",
        "gainer_previous_gold_price": "",
        "secondary_market_mode": "mixed",
        "secondary_use_default_dates": True,
        "secondary_start_date": secondary_start_date,
        "secondary_end_date": secondary_end_date,
        **overall_defaults,
        "result": None,
        "active_job_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _sanitize_text_path(value: object, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _restore_overall_paths(config) -> None:
    for key, default in _default_overall_paths(config).items():
        st.session_state[key] = _sanitize_text_path(st.session_state.get(key), default)


def _restore_gainer_inputs() -> None:
    default_current_date = _current_week_saturday()
    default_previous_date = default_current_date - timedelta(days=14)
    current_date = st.session_state.get("gainer_current_date", default_current_date)
    previous_date = st.session_state.get("gainer_previous_date", default_previous_date)
    if not isinstance(current_date, date):
        current_date = default_current_date
    if not isinstance(previous_date, date):
        previous_date = default_previous_date
    st.session_state["gainer_current_date"] = current_date
    st.session_state["gainer_previous_date"] = previous_date
    selected_modules = [
        key for key, _ in GAINER_MODULE_OPTIONS if key in st.session_state.get("gainer_modules", [])
    ]
    st.session_state["gainer_modules"] = selected_modules or [key for key, _ in GAINER_MODULE_OPTIONS]
    selected_stock_markets = [
        key for key, _ in STOCK_MARKET_OPTIONS if key in st.session_state.get("gainer_stock_markets", [])
    ]
    st.session_state["gainer_stock_markets"] = selected_stock_markets or [key for key, _ in STOCK_MARKET_OPTIONS]
    st.session_state["gainer_current_gold_price"] = str(
        st.session_state.get("gainer_current_gold_price", "")
    ).strip()
    st.session_state["gainer_previous_gold_price"] = str(
        st.session_state.get("gainer_previous_gold_price", "")
    ).strip()


def _validate_gainer_date(field_key: str, label: str) -> date | None:
    value = st.session_state.get(field_key)
    if not isinstance(value, date):
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": f"{label} 读取失败，请重新从日历中选择一个周六日期。",
            "traceback": "",
        }
        return None
    if value.weekday() != 5:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": f"{label} 必须选择周六，请重新从日历中选择周六日期。",
            "traceback": "",
        }
        return None
    return value


def _parse_gainer_price(field_key: str, label: str) -> float | None:
    raw = str(st.session_state.get(field_key, "")).strip()
    if not raw:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": f"{label} 不能为空，请填写 LBMA Gold Price PM（USD/oz）。",
            "traceback": "",
        }
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": f"{label} 格式无效，请填写数值，例如 2378.42。",
            "traceback": "",
        }
        return None


def _create_job_payload(label: str) -> dict[str, object]:
    return {
        "label": label,
        "state": "queued",
        "started_at": time.time(),
        "finished_at": None,
        "cancel_requested": False,
        "current_unit": None,
        "current_subtask": None,
        "current_subtask_ratio": None,
        "current_subtask_label": "",
        "total_units": 0,
        "completed_units": [],
        "pending_units": [],
        "progress_ratio": 0.0,
        "logs": [],
        "result": None,
        "traceback": "",
    }


def _set_job(job_id: str, payload: dict[str, object]) -> None:
    with _JOB_LOCK:
        _JOB_REGISTRY[job_id] = payload


def _get_job(job_id: str | None) -> dict[str, object] | None:
    if not job_id:
        return None
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        return deepcopy(job) if job else None


def _update_job(job_id: str, **updates: object) -> None:
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job:
            return
        job.update(updates)


def _append_job_logs(job_id: str, raw_text: str) -> None:
    cleaned = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
    if not cleaned:
        return
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job:
            return
        logs = list(job.get("logs", []))
        logs.extend(cleaned)
        job["logs"] = logs[-120:]


def _request_job_cancel(job_id: str | None) -> None:
    if not job_id:
        return
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job or job.get("state") in {"success", "error", "cancelled"}:
            return
        job["cancel_requested"] = True
        job["state"] = "cancelling"
        logs = list(job.get("logs", []))
        logs.append("收到取消请求，正在等待当前步骤安全结束。")
        job["logs"] = logs[-120:]


def _cancel_active_job() -> None:
    _request_job_cancel(st.session_state.get("active_job_id"))


def _job_cancel_requested(job_id: str) -> bool:
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        return bool(job and job.get("cancel_requested"))


def _format_event_log(event: dict[str, object]) -> str | None:
    event_type = event.get("event")
    if event_type == "module_start":
        return f"开始模块：{MODULE_LABELS.get(str(event.get('module_name')), event.get('module_name', ''))}"
    if event_type == "module_complete":
        return f"完成模块：{MODULE_LABELS.get(str(event.get('module_name')), event.get('module_name', ''))}"
    if event_type == "module_error":
        return f"模块失败：{MODULE_LABELS.get(str(event.get('module_name')), event.get('module_name', ''))} - {event.get('message', '')}"
    if event_type == "step_start":
        return f"开始 {event.get('step_label', '')}"
    if event_type == "step_complete":
        return f"完成 {event.get('step_label', '')}"
    if event_type == "subtask_start":
        return str(event.get("progress_label", "")).strip() or None
    if event_type == "subtask_complete":
        return str(event.get("progress_label", "")).strip() or None
    return None


def _apply_progress_event(job_id: str, event: dict[str, object]) -> None:
    event_type = str(event.get("event", "")).strip()
    human_log = _format_event_log(event)
    if human_log:
        _append_job_logs(job_id, human_log)

    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        if not job:
            return

        if event_type == "job_init":
            job["total_units"] = int(event.get("total_units", 0) or 0)
            job["pending_units"] = list(event.get("pending_units", []))
            return

        if event_type in {"module_start", "step_start"}:
            job["current_unit"] = event.get("module_name") or event.get("step_label")
            job["completed_units"] = list(event.get("completed_units", job.get("completed_units", [])))
            job["pending_units"] = list(event.get("pending_units", job.get("pending_units", [])))
            job["progress_ratio"] = float(event.get("progress_ratio", job.get("progress_ratio", 0.0)) or 0.0)
            job["current_subtask"] = None
            job["current_subtask_ratio"] = None
            job["current_subtask_label"] = ""
            return

        if event_type in {"module_complete", "step_complete"}:
            job["current_unit"] = event.get("module_name") or event.get("step_label")
            job["completed_units"] = list(event.get("completed_units", job.get("completed_units", [])))
            job["pending_units"] = list(event.get("pending_units", job.get("pending_units", [])))
            job["progress_ratio"] = float(event.get("progress_ratio", job.get("progress_ratio", 0.0)) or 0.0)
            job["current_subtask"] = None
            job["current_subtask_ratio"] = None
            job["current_subtask_label"] = ""
            return

        if event_type == "module_error":
            job["current_unit"] = event.get("module_name")
            job["traceback"] = str(event.get("message", ""))
            return

        if event_type in {"subtask_start", "subtask_progress", "subtask_complete"}:
            job["current_subtask"] = event.get("subtask")
            job["current_subtask_ratio"] = float(event.get("progress_ratio", 0.0) or 0.0)
            job["current_subtask_label"] = str(event.get("progress_label", "") or "")


class _StreamingJobCapture(io.TextIOBase):
    def __init__(self, sink: io.StringIO, job_id: str):
        self._sink = sink
        self._job_id = job_id
        self._pending = ""

    def write(self, text: str) -> int:
        self._sink.write(text)
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", maxsplit=1)
            _append_job_logs(self._job_id, line)
        return len(text)

    def flush(self) -> None:
        if self._pending.strip():
            _append_job_logs(self._job_id, self._pending.strip())
        self._pending = ""
        self._sink.flush()


def _sync_background_result() -> None:
    job_id = st.session_state.get("active_job_id")
    job = _get_job(job_id)
    if not job:
        return
    if job["state"] in {"success", "error", "cancelled"}:
        st.session_state["result"] = deepcopy(job["result"])
        st.session_state["active_job_id"] = None


def _capture_run(label: str, callback, job_id: str):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    start = time.perf_counter()
    out_stream = _StreamingJobCapture(stdout_buffer, job_id)
    err_stream = _StreamingJobCapture(stderr_buffer, job_id)
    try:
        with redirect_stdout(out_stream), redirect_stderr(err_stream):
            callback(
                lambda event: _apply_progress_event(job_id, event),
                lambda: _job_cancel_requested(job_id),
            )
    except JobCancelledError:
        return {
            "label": label,
            "status": "cancelled",
            "duration": time.perf_counter() - start,
            "output": (stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()).strip(),
            "traceback": "",
        }
    except Exception:
        return {
            "label": label,
            "status": "error",
            "duration": time.perf_counter() - start,
            "output": (stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()).strip(),
            "traceback": traceback.format_exc(),
        }
    finally:
        out_stream.flush()
        err_stream.flush()
    return {
        "label": label,
        "status": "success",
        "duration": time.perf_counter() - start,
        "output": (stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()).strip(),
        "traceback": "",
    }


def _start_background_job(label: str, callback) -> None:
    current_job = _get_job(st.session_state.get("active_job_id"))
    if current_job and current_job["state"] in {"running", "cancelling"}:
        st.session_state["result"] = {
            "label": label,
            "status": "error",
            "duration": 0.0,
            "output": f"{current_job['label']} 仍在运行，请先等待当前任务结束。",
            "traceback": "",
        }
        return

    job_id = uuid4().hex
    payload = _create_job_payload(label)
    payload["state"] = "running"
    _set_job(job_id, payload)

    def _runner() -> None:
        result = _capture_run(label, callback, job_id)
        end_state = result["status"]
        _update_job(
            job_id,
            state=end_state,
            finished_at=time.time(),
            result=result,
            traceback=result["traceback"],
            progress_ratio=1.0 if end_state == "success" else _get_job(job_id).get("progress_ratio", 0.0),
        )

    Thread(target=_runner, daemon=True).start()
    st.session_state["active_job_id"] = job_id
    st.session_state["result"] = {
        "label": label,
        "status": "running",
        "duration": 0.0,
        "output": "任务已提交到后台。",
        "traceback": "",
    }

def _set_workspace(workspace: str) -> None:
    workspace = _normalize_workspace(workspace)
    st.session_state["active_workspace"] = workspace


@contextmanager
def _temporary_env(debug: bool, use_proxy: bool):
    updates = {
        "AMR_DEBUG": "true" if debug else "false",
        "AMR_USE_PROXY": "true" if use_proxy else "false",
    }
    snapshot = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, old_value in snapshot.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def _patched_config(module, **updates):
    original = deepcopy(module.CONFIG)
    module.CONFIG.update({key: value for key, value in updates.items() if value is not None})
    try:
        yield
    finally:
        module.CONFIG.clear()
        module.CONFIG.update(original)


def _run_main_action() -> None:
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])
    modules = list(st.session_state["main_modules"])
    stock_markets = list(st.session_state["main_stock_markets"])
    if "stock_index" in modules and not stock_markets:
        st.session_state["result"] = {
            "label": "主报表",
            "status": "error",
            "duration": 0.0,
            "output": "股票权益模块至少需要选择一个股票市场。",
            "traceback": "",
        }
        return

    def _job(progress_callback, cancel_check) -> None:
        with _temporary_env(debug, use_proxy):
            main_entry.main(
                debug=debug,
                modules=modules,
                stock_markets=stock_markets,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

    _start_background_job("主报表", _job)


def _run_gainer_action() -> None:
    selected_modules = list(st.session_state["gainer_modules"])
    if not selected_modules:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": "请至少选择一个 Gainer 子模块。",
            "traceback": "",
        }
        return
    selected_stock_markets = list(st.session_state["gainer_stock_markets"])
    if "stocks" in selected_modules and not selected_stock_markets:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": "股票子模块至少需要选择一个股票市场。",
            "traceback": "",
        }
        return
    current_date = _validate_gainer_date("gainer_current_date", "本周末日期（周六）")
    previous_date = _validate_gainer_date("gainer_previous_date", "两周前日期（周六）")
    current_gold = previous_gold = None
    if "gold" in selected_modules:
        current_gold = _parse_gainer_price("gainer_current_gold_price", "本周末黄金价格")
        previous_gold = _parse_gainer_price("gainer_previous_gold_price", "两周前黄金价格")
    if current_date is None or previous_date is None or ("gold" in selected_modules and None in {current_gold, previous_gold}):
        return
    if (current_date - previous_date).days != 14:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": "两周前日期需要与本周末日期相差 14 天，并且两者都必须是周六。",
            "traceback": "",
        }
        return

    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])

    def _job(progress_callback, cancel_check) -> None:
        with _patched_config(
            gainer_entry,
            modules=selected_modules,
            stock_markets=selected_stock_markets,
            current_date=current_date,
            previous_date=previous_date,
            current_gold_price=current_gold,
            previous_gold_price=previous_gold,
        ):
            with _temporary_env(debug, use_proxy):
                gainer_entry.main(
                    modules=selected_modules,
                    stock_markets=selected_stock_markets,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )

    _start_background_job("Gainer", _job)


def _run_secondary_market_action() -> None:
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])
    market_mode = st.session_state.get("secondary_market_mode", "mixed")
    use_default_dates = bool(st.session_state.get("secondary_use_default_dates", True))
    start_date = st.session_state.get("secondary_start_date")
    end_date = st.session_state.get("secondary_end_date")
    if not use_default_dates:
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            st.session_state["result"] = {
                "label": "二级市场",
                "status": "error",
                "duration": 0.0,
                "output": "请先选择有效的开始和结束日期。",
                "traceback": "",
            }
            return
        if start_date >= end_date:
            st.session_state["result"] = {
                "label": "二级市场",
                "status": "error",
                "duration": 0.0,
                "output": "开始日期必须早于结束日期。",
                "traceback": "",
            }
            return

    def _job(progress_callback, cancel_check) -> None:
        del progress_callback, cancel_check
        with _temporary_env(debug, use_proxy):
            secondary_market_entry.main(
                market_mode=market_mode,
                use_default_dates=use_default_dates,
                start_date=start_date.isoformat() if isinstance(start_date, date) else None,
                end_date=end_date.isoformat() if isinstance(end_date, date) else None,
            )

    _start_background_job("二级市场", _job)


def _run_overall_action(config) -> None:
    defaults = _default_overall_paths(config)
    input_path = Path(_sanitize_text_path(st.session_state.get("overall_input_path_text"), defaults["overall_input_path_text"]))
    output_path = Path(_sanitize_text_path(st.session_state.get("overall_output_path_text"), defaults["overall_output_path_text"]))
    log_path = Path(_sanitize_text_path(st.session_state.get("overall_log_path_text"), defaults["overall_log_path_text"]))
    if input_path.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        st.session_state["result"] = {
            "label": "整体表",
            "status": "error",
            "duration": 0.0,
            "output": f"输入文件必须是 Excel 文件，当前为: {input_path}",
            "traceback": "",
        }
        return
    if not input_path.exists():
        st.session_state["result"] = {
            "label": "整体表",
            "status": "error",
            "duration": 0.0,
            "output": f"未找到输入文件: {input_path}",
            "traceback": "",
        }
        return

    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])

    def _job(progress_callback, cancel_check) -> None:
        if cancel_check():
            raise JobCancelledError("任务已被取消。")
        with _patched_config(
            overall_entry,
            input_path=input_path,
            output_path=output_path,
            log_path=log_path,
        ):
            with _temporary_env(debug, use_proxy):
                overall_entry.main()
        if cancel_check():
            raise JobCancelledError("任务已被取消。")

    _start_background_job("整体表", _job)


def _run_validation_action() -> None:
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])

    def _job(progress_callback, cancel_check) -> None:
        if cancel_check():
            raise JobCancelledError("任务已被取消。")
        with _temporary_env(debug, use_proxy):
            validate_outputs.main()
        if cancel_check():
            raise JobCancelledError("任务已被取消。")

    _start_background_job("全量校验", _job)


def _format_unit_items(items: list[object]) -> str:
    formatted: list[str] = []
    for item in items:
        text = str(item)
        formatted.append(MODULE_LABELS.get(text, text))
    return "、".join(formatted) if formatted else "无"


def _render_job_snapshot(job: dict[str, object]) -> None:
    elapsed = max(0.0, time.time() - float(job["started_at"]))
    state = str(job.get("state", "running"))
    if state == "running":
        state_text = "运行中"
        state_color = "#b7791f"
    elif state == "cancelling":
        state_text = "取消中"
        state_color = "#8b5e15"
    elif state == "cancelled":
        state_text = "已取消"
        state_color = "#8f2d2d"
    elif state == "success":
        state_text = "成功"
        state_color = "#176b4d"
    else:
        state_text = "失败"
        state_color = "#8f2d2d"

    st.markdown(
        f"""
        <div class="amr-result">
            <strong style="color:{state_color};">{job["label"]} · {state_text}</strong><br />
            已持续 {elapsed:.1f} 秒
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(float(job.get("progress_ratio", 0.0) or 0.0), text=f"总体进度 {float(job.get('progress_ratio', 0.0) or 0.0) * 100:.0f}%")
    if job.get("current_unit"):
        st.caption(f"当前模块 / 步骤：{MODULE_LABELS.get(str(job['current_unit']), str(job['current_unit']))}")
    if job.get("current_subtask_label"):
        st.progress(
            float(job.get("current_subtask_ratio", 0.0) or 0.0),
            text=f"当前子任务：{job['current_subtask_label']}",
        )
    info_cols = st.columns(2)
    info_cols[0].caption(f"已完成：{_format_unit_items(list(job.get('completed_units', [])))}")
    info_cols[1].caption(f"待执行：{_format_unit_items(list(job.get('pending_units', [])))}")
    if state in {"running", "cancelling"}:
        if state == "running":
            st.info("任务正在后台运行，页面会自动刷新。")
        else:
            st.warning("正在取消任务，等待当前步骤安全结束。")
        action_cols = st.columns(3)
        action_cols[0].button("刷新状态", key=f"refresh-{job['label']}", use_container_width=True)
        action_cols[1].button(
            "取消当前任务",
            key=f"cancel-{job['label']}",
            use_container_width=True,
            on_click=_cancel_active_job,
        )
        action_cols[2].button(
            "返回概览",
            key=f"home-while-running-{job['label']}",
            use_container_width=True,
            on_click=_set_workspace,
            args=("home",),
        )
    logs = "\n".join(list(job.get("logs", []))[-24:])
    if logs:
        st.code(logs, language="text")


@st.fragment(run_every="2s")
def _render_result_panel() -> None:
    _sync_background_result()
    active_job = _get_job(st.session_state.get("active_job_id"))
    if active_job:
        _render_job_snapshot(active_job)
        return

    result = st.session_state.get("result")
    if not result:
        return

    if result["status"] == "cancelled":
        status_text = "已取消"
        status_color = "#8f2d2d"
    else:
        status_text = "成功" if result["status"] == "success" else "失败"
        status_color = "#176b4d" if result["status"] == "success" else "#8f2d2d"
    st.markdown(
        f"""
        <div class="amr-result">
            <strong style="color:{status_color};">{result["label"]} · {status_text}</strong><br />
            用时 {result["duration"]:.2f} 秒
        </div>
        """,
        unsafe_allow_html=True,
    )
    if result["output"]:
        st.code(result["output"], language="text")
    if result["traceback"]:
        st.error(result["traceback"])


def _clear_result() -> None:
    st.session_state["result"] = None


def _render_sidebar(config) -> None:
    with st.sidebar:
        st.markdown("### 控制台设置")
        st.caption("主页进入工作台，运行状态自动刷新。")
        st.checkbox("启用 debug", key="debug")
        st.checkbox("启用代理", key="use_proxy")
        st.button(
            "清空结果面板",
            key="clear-result-sidebar",
            use_container_width=True,
            on_click=_clear_result,
        )

        st.markdown("---")
        active_job = _get_job(st.session_state.get("active_job_id"))
        if active_job and active_job["state"] in {"running", "cancelling"}:
            st.markdown("#### 后台任务")
            st.caption(f"{active_job['label']} · {'取消中' if active_job['state'] == 'cancelling' else '运行中'}")
            st.caption(f"已持续 {max(0.0, time.time() - float(active_job['started_at'])):.1f} 秒")
            if active_job.get("current_unit"):
                st.caption(f"当前：{MODULE_LABELS.get(str(active_job['current_unit']), str(active_job['current_unit']))}")
            st.progress(float(active_job.get("progress_ratio", 0.0) or 0.0))
            st.button("刷新状态", key="refresh-sidebar", use_container_width=True)
            st.button("取消当前任务", key="cancel-sidebar", use_container_width=True, on_click=_cancel_active_job)
            st.markdown("---")
        st.markdown("#### 当前目录")
        st.caption(f"项目根目录: `{config.project_root}`")
        st.caption(f"种子数据目录: `{config.seed_data_dir}`")
        st.caption(f"本地数据目录: `{config.local_data_dir}`")
        st.caption(f"输出目录: `{config.output_dir}`")


def _render_workspace_header(title: str, description: str) -> None:
    left, right = st.columns([5, 1.25])
    with left:
        st.markdown(
            f"""
            <div class="amr-workspace-copy">
                <h2>{title}</h2>
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.button(
            "返回概览",
            key=f"back-{title}",
            use_container_width=True,
            on_click=_set_workspace,
            args=("home",),
        )


def _render_home() -> None:
    st.markdown(
        """
        <section class="amr-hero">
            <div class="amr-eyebrow">Asset Management Report</div>
            <h1>资产管理报表控制台</h1>
            <p>
                统一参数驱动主报表、Gainer、整体表与校验。
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="amr-section-label">工作入口</div>', unsafe_allow_html=True)
    columns = st.columns(2, gap="large")
    for index, (page_key, title, desc) in enumerate(HOME_CARDS):
        with columns[index % 2]:
            st.markdown(f'<div class="amr-panel"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
            st.button(
                f"打开 {title}",
                key=f"workspace-{page_key}",
                use_container_width=True,
                type="primary",
                on_click=_set_workspace,
                args=(page_key,),
            )

    st.markdown('<div class="amr-section-label">当前默认行为</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="amr-panel">
            <h3>交互逻辑</h3>
            <p>
                后台任务会自动刷新状态，支持查看已完成模块、当前步骤和运行日志。
            </p>
            <div class="amr-meta">
                默认启用代理。长任务可取消，结果与日志会保留在页面中。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="amr-inline-note">执行过程中可随时查看日志、刷新状态或返回主页。</div>',
        unsafe_allow_html=True,
    )


def _render_main_page() -> None:
    _render_workspace_header("主报表工作台", "选择模块并运行，页面会显示已完成模块与当前进度。")
    st.multiselect(
        "主报表模块",
        options=[key for key, _ in MODULE_OPTIONS],
        default=st.session_state["main_modules"],
        key="main_modules",
        format_func=lambda key: f"{MODULE_LABELS[key]} · {key}",
    )
    st.multiselect(
        "股票权益市场",
        options=[key for key, _ in STOCK_MARKET_OPTIONS],
        default=st.session_state["main_stock_markets"],
        key="main_stock_markets",
        format_func=lambda key: f"{STOCK_MARKET_LABELS[key]} · {key}",
        help="仅对主报表中的“股票权益”模块生效。",
        disabled="stock_index" not in st.session_state.get("main_modules", []),
    )
    if st.button("执行主报表", key="run-main", type="primary", use_container_width=True):
        _run_main_action()
    _render_result_panel()


def _render_gainer_page() -> None:
    _restore_gainer_inputs()
    _render_workspace_header("Gainer 工作台", "请选择两个周六日期并填写金价，页面会显示步骤进度与日志。")
    st.multiselect(
        "Gainer 子模块",
        options=[key for key, _ in GAINER_MODULE_OPTIONS],
        default=st.session_state["gainer_modules"],
        key="gainer_modules",
        format_func=lambda key: f"{GAINER_MODULE_LABELS[key]} · {key}",
    )
    st.multiselect(
        "股票子模块市场",
        options=[key for key, _ in STOCK_MARKET_OPTIONS],
        default=st.session_state["gainer_stock_markets"],
        key="gainer_stock_markets",
        format_func=lambda key: f"{STOCK_MARKET_LABELS[key]} · {key}",
        disabled="stocks" not in st.session_state.get("gainer_modules", []),
        help="仅在勾选股票子模块时生效。",
    )
    st.markdown(
        """
        <div class="amr-inline-note">
            黄金价格请参考 LBMA Gold Price 页面，选择 <strong>USD PM</strong> 后填入页面中的两个价格框。
            参考网址：<a href="https://www.lbma.org.uk/prices-and-data#/" target="_blank">lbma.org.uk/prices-and-data#/</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    col1.date_input(
        "本周末日期（周六）",
        key="gainer_current_date",
        help="请选择本周对应的周六日期。",
    )
    col2.date_input(
        "两周前日期（周六）",
        key="gainer_previous_date",
        help="请选择与本周末日期相差 14 天的周六日期。",
    )
    col3, col4 = st.columns(2)
    gold_disabled = "gold" not in st.session_state.get("gainer_modules", [])
    col3.text_input(
        "本周末黄金价格（USD/oz）",
        key="gainer_current_gold_price",
        placeholder="例如 2378.42",
        disabled=gold_disabled,
    )
    col4.text_input(
        "两周前黄金价格（USD/oz）",
        key="gainer_previous_gold_price",
        placeholder="例如 2314.15",
        disabled=gold_disabled,
    )
    if st.button("执行 Gainer", key="run-gainer", type="primary", use_container_width=True):
        _run_gainer_action()
    _render_result_panel()


def _render_secondary_market_page() -> None:
    _render_workspace_header("二级市场工作台", "单独运行美股 / 中港股 / 混合二级市场两周报表。")
    st.selectbox(
        "市场模式",
        options=[key for key, _ in SECONDARY_MARKET_MODE_OPTIONS],
        key="secondary_market_mode",
        format_func=lambda key: f"{SECONDARY_MARKET_MODE_LABELS[key]} · {key}",
    )
    st.checkbox("使用智能默认日期", key="secondary_use_default_dates")
    date_disabled = bool(st.session_state.get("secondary_use_default_dates", True))
    col1, col2 = st.columns(2)
    col1.date_input("开始日期", key="secondary_start_date", disabled=date_disabled)
    col2.date_input("结束日期", key="secondary_end_date", disabled=date_disabled)
    if st.button("执行二级市场报表", key="run-secondary-market", type="primary", use_container_width=True):
        _run_secondary_market_action()
    _render_result_panel()


def _render_overall_page(config) -> None:
    _restore_overall_paths(config)
    _render_workspace_header("整体表工作台", "处理整体.xlsx，并输出处理后的总表与日志。")
    st.text_input("输入文件", key="overall_input_path_text")
    st.text_input("输出文件", key="overall_output_path_text")
    st.text_input("日志文件", key="overall_log_path_text")
    cols = st.columns(2)
    cols[0].button("恢复默认路径", key="restore-overall-defaults", use_container_width=True, on_click=_restore_overall_paths, args=(config,))
    if cols[1].button("执行整体表", key="run-overall", type="primary", use_container_width=True):
        _run_overall_action(config)
    _render_result_panel()


def _render_validation_page() -> None:
    _render_workspace_header("校验工作台", "对 main / codex 输出执行回归比较，并刷新对比报告。")
    st.markdown(
        """
        <div class="amr-panel">
            <h3>校验范围</h3>
            <p>
                当前覆盖主报表、Gainer、整体表和二级市场核心输出。校验报告会更新到
                <code>docs/重构前后对比报告.md</code>。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("执行全量校验", type="primary", use_container_width=True):
        _run_validation_action()
    _render_result_panel()


def render_app() -> None:
    config = build_app_config()
    st.set_page_config(page_title="Asset Management Report", page_icon="📊", layout="wide")
    _inject_styles()
    _ensure_state(config)
    _sync_background_result()
    _render_sidebar(config)

    active_workspace = st.session_state["active_workspace"]
    if active_workspace == "home":
        _render_home()
    elif active_workspace == "main":
        _render_main_page()
    elif active_workspace == "gainer":
        _render_gainer_page()
    elif active_workspace == "secondary_market":
        _render_secondary_market_page()
    elif active_workspace == "overall":
        _render_overall_page(config)
    elif active_workspace == "validation":
        _render_validation_page()
    else:
        st.session_state["active_workspace"] = "home"
        _render_home()


if __name__ == "__main__":
    render_app()
