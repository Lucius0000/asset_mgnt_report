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
from scripts.validation import validate_outputs
from src.asset_mgnt_report.config.defaults import build_app_config


MODULE_OPTIONS: list[tuple[str, str]] = [
    ("cpi", "CPI"),
    ("gdp", "GDP"),
    ("interest_rate", "利率"),
    ("carry_trade", "利差"),
    ("stock_index", "股票权益"),
    ("currency", "汇率"),
    ("precious_metals", "商品与贵金属"),
    ("bonds", "债券固收"),
    ("crypto", "数字货币"),
]
MODULE_LABELS = {key: label for key, label in MODULE_OPTIONS}
HOME_CARDS = [
    ("main", "主报表工作台", "按模块执行周报主链路，适合日常更新。"),
    ("gainer", "Gainer 工作台", "输入日期与金价，稳定生成跨资产 Gainer 汇总。"),
    ("overall", "整体表工作台", "处理整体.xlsx 并输出整体_processed.xlsx。"),
    ("validation", "校验工作台", "对 main / codex 输出做回归对比，更新对比报告。"),
]
WORKSPACE_LABELS = {
    "home": "主页",
    "main": "主报表",
    "gainer": "Gainer",
    "overall": "整体表",
    "validation": "全量校验",
}
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
    if workspace in {"home", "main", "gainer", "overall", "validation"}:
        return workspace
    return "home"


def _default_overall_paths(config) -> dict[str, str]:
    return {
        "overall_input_path_text": str(config.seed_data_dir / "整体.xlsx"),
        "overall_output_path_text": str(config.output_dir / "整体_processed.xlsx"),
        "overall_log_path_text": str(config.raw_output_dir / "整体_calculation_steps.txt"),
    }


def _ensure_state(config) -> None:
    overall_defaults = _default_overall_paths(config)
    defaults = {
        "active_workspace": _normalize_workspace(os.getenv("AMR_ACTIVE_WORKSPACE")),
        "debug": config.debug,
        "use_proxy": config.use_proxy,
        "main_modules": [key for key, _ in MODULE_OPTIONS],
        "gainer_current_date": date.today(),
        "gainer_previous_date": date.today() - timedelta(days=13),
        "gainer_current_gold_price": "",
        "gainer_previous_gold_price": "",
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


def _set_job(job_id: str, payload: dict[str, object]) -> None:
    with _JOB_LOCK:
        _JOB_REGISTRY[job_id] = payload


def _get_job(job_id: str | None) -> dict[str, object] | None:
    if not job_id:
        return None
    with _JOB_LOCK:
        job = _JOB_REGISTRY.get(job_id)
        return deepcopy(job) if job else None


def _sync_background_result() -> None:
    job_id = st.session_state.get("active_job_id")
    job = _get_job(job_id)
    if not job:
        return
    if job["state"] == "finished":
        st.session_state["result"] = deepcopy(job["result"])
        st.session_state["active_job_id"] = None


def _start_background_job(label: str, callback) -> None:
    current_job = _get_job(st.session_state.get("active_job_id"))
    if current_job and current_job["state"] == "running":
        st.session_state["result"] = {
            "label": label,
            "status": "error",
            "duration": 0.0,
            "output": f"{current_job['label']} 仍在运行，请先等待当前任务结束。",
            "traceback": "",
        }
        return

    job_id = uuid4().hex
    _set_job(
        job_id,
        {
            "state": "running",
            "label": label,
            "started_at": time.time(),
            "result": None,
        },
    )

    def _runner() -> None:
        result = _capture_run(label, callback)
        _set_job(
            job_id,
            {
                "state": "finished",
                "label": label,
                "started_at": _get_job(job_id)["started_at"] if _get_job(job_id) else time.time(),
                "result": result,
            },
        )

    Thread(target=_runner, daemon=True).start()
    st.session_state["active_job_id"] = job_id
    st.session_state["result"] = {
        "label": label,
        "status": "running",
        "duration": 0.0,
        "output": "任务已提交到后台。你可以留在当前页查看状态，也可以返回主页后稍后刷新。",
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


def _capture_run(label: str, callback):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    start = time.perf_counter()
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            callback()
    except Exception:
        return {
            "label": label,
            "status": "error",
            "duration": time.perf_counter() - start,
            "output": (stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()).strip(),
            "traceback": traceback.format_exc(),
        }
    return {
        "label": label,
        "status": "success",
        "duration": time.perf_counter() - start,
        "output": (stdout_buffer.getvalue() + "\n" + stderr_buffer.getvalue()).strip(),
        "traceback": "",
    }


def _run_main_action() -> None:
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])
    modules = list(st.session_state["main_modules"])

    def _job() -> None:
        with _temporary_env(debug, use_proxy):
            main_entry.main(debug=debug, modules=modules)

    _start_background_job("主报表", _job)


def _run_gainer_action() -> None:
    if not st.session_state["gainer_current_gold_price"] or not st.session_state["gainer_previous_gold_price"]:
        st.session_state["result"] = {
            "label": "Gainer",
            "status": "error",
            "duration": 0.0,
            "output": "运行 Gainer 之前，需要在页面中填写本周末与两周前的黄金价格。",
            "traceback": "",
        }
        return

    current_date = st.session_state["gainer_current_date"].strftime("%Y-%m-%d")
    previous_date = st.session_state["gainer_previous_date"].strftime("%Y-%m-%d")
    current_gold = float(st.session_state["gainer_current_gold_price"])
    previous_gold = float(st.session_state["gainer_previous_gold_price"])
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])

    def _job() -> None:
        with _patched_config(
            gainer_entry,
            current_date=current_date,
            previous_date=previous_date,
            current_gold_price=current_gold,
            previous_gold_price=previous_gold,
        ):
            with _temporary_env(debug, use_proxy):
                gainer_entry.main()

    _start_background_job("Gainer", _job)


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

    def _job() -> None:
        with _patched_config(
            overall_entry,
            input_path=input_path,
            output_path=output_path,
            log_path=log_path,
        ):
            with _temporary_env(debug, use_proxy):
                overall_entry.main()

    _start_background_job("整体表", _job)


def _run_validation_action() -> None:
    debug = bool(st.session_state["debug"])
    use_proxy = bool(st.session_state["use_proxy"])

    def _job() -> None:
        with _temporary_env(debug, use_proxy):
            validate_outputs.main()

    _start_background_job("全量校验", _job)


def _render_result_panel() -> None:
    active_job = _get_job(st.session_state.get("active_job_id"))
    if active_job and active_job["state"] == "running":
        elapsed = max(0.0, time.time() - float(active_job["started_at"]))
        st.markdown(
            f"""
            <div class="amr-result">
                <strong style="color:#b7791f;">{active_job["label"]} · 运行中</strong><br />
                已持续 {elapsed:.1f} 秒
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info("任务正在后台运行。可以点击“刷新状态”查看最新结果，或返回主页继续其他操作。")
        cols = st.columns(2)
        cols[0].button("刷新状态", key=f"refresh-{active_job['label']}", use_container_width=True)
        cols[1].button(
            "返回概览",
            key=f"home-while-running-{active_job['label']}",
            use_container_width=True,
            on_click=_set_workspace,
            args=("home",),
        )
        if st.session_state.get("result", {}).get("status") == "running":
            st.code(st.session_state["result"]["output"], language="text")
        return

    result = st.session_state.get("result")
    if not result:
        return

    if result["status"] == "running":
        status_text = "运行中"
        status_color = "#b7791f"
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
        st.caption("工作台从主页卡片进入，当前页内展开。")
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
        if active_job and active_job["state"] == "running":
            st.markdown("#### 后台任务")
            st.caption(f"{active_job['label']} 运行中")
            st.caption(f"已持续 {max(0.0, time.time() - float(active_job['started_at'])):.1f} 秒")
            st.button("刷新状态", key="refresh-sidebar", use_container_width=True)
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
                以统一参数和统一口径驱动主报表、Gainer、整体表与回归校验。
                页面默认以代理模式运行，避免数据抓取链路在日常使用中反复手动切换。
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
                主页负责导航；各工作台负责参数编辑和执行；所有执行结果固定显示在结果区，不再因按钮触发而出现整页空白。
            </p>
            <div class="amr-meta">
                默认启用代理。运行结果、报错和日志都会停留在页面中，便于复核和回退。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="amr-inline-note">如果任务执行失败，错误日志会保留在当前页，不会再跳成空白页面。</div>',
        unsafe_allow_html=True,
    )


def _render_main_page() -> None:
    _render_workspace_header("主报表工作台", "选择需要执行的资产模块，运行结果会固定停留在当前页底部。")
    st.multiselect(
        "主报表模块",
        options=[key for key, _ in MODULE_OPTIONS],
        default=st.session_state["main_modules"],
        key="main_modules",
        format_func=lambda key: f"{MODULE_LABELS[key]} · {key}",
    )
    if st.button("执行主报表", key="run-main", type="primary", use_container_width=True):
        _run_main_action()
    _render_result_panel()


def _render_gainer_page() -> None:
    _render_workspace_header("Gainer 工作台", "在页面中直接定义日期和黄金价格，避免后台脚本再回退到命令行交互。")
    col1, col2 = st.columns(2)
    col1.date_input("本周末日期", key="gainer_current_date")
    col2.date_input("两周前日期", key="gainer_previous_date")
    col3, col4 = st.columns(2)
    col3.text_input("本周末黄金价格（USD/oz）", key="gainer_current_gold_price", placeholder="例如 2378.42")
    col4.text_input("两周前黄金价格（USD/oz）", key="gainer_previous_gold_price", placeholder="例如 2314.15")
    if st.button("执行 Gainer", key="run-gainer", type="primary", use_container_width=True):
        _run_gainer_action()
    _render_result_panel()


def _render_overall_page(config) -> None:
    _restore_overall_paths(config)
    _render_workspace_header("整体表工作台", "处理整理好的整体.xlsx 输入，并稳定输出处理后的总表与日志。")
    st.text_input("输入文件", key="overall_input_path_text")
    st.text_input("输出文件", key="overall_output_path_text")
    st.text_input("日志文件", key="overall_log_path_text")
    cols = st.columns(2)
    cols[0].button("恢复默认路径", key="restore-overall-defaults", use_container_width=True, on_click=_restore_overall_paths, args=(config,))
    if cols[1].button("执行整体表", key="run-overall", type="primary", use_container_width=True):
        _run_overall_action(config)
    _render_result_panel()


def _render_validation_page() -> None:
    _render_workspace_header("校验工作台", "对 main / codex 已落盘输出执行回归比较，并刷新对比报告。")
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
    elif active_workspace == "overall":
        _render_overall_page(config)
    elif active_workspace == "validation":
        _render_validation_page()
    else:
        st.session_state["active_workspace"] = "home"
        _render_home()


if __name__ == "__main__":
    render_app()
