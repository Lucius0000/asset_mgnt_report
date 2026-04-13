from streamlit.testing.v1 import AppTest

from src.asset_mgnt_report.config.defaults import build_app_config
from src.asset_mgnt_report.ui import streamlit_app


APP_FILE = "scripts/web_ui.py"


def _run_page(page: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_FILE)
    if page is not None:
        at.session_state["active_workspace"] = page
    at.run()
    return at


def test_web_ui_home_renders_with_proxy_enabled() -> None:
    at = _run_page()

    assert not at.exception
    assert len(at.checkbox) >= 2
    assert at.checkbox[1].label == "启用代理"
    assert at.checkbox[1].value is True
    rendered_markdown = "\n".join(markdown.value for markdown in at.markdown)
    assert "主报表工作台" in rendered_markdown
    assert "Gainer 工作台" in rendered_markdown
    assert any(button.label == "打开 主报表工作台" for button in at.button)


def test_home_button_navigates_to_main_workspace() -> None:
    at = _run_page()

    next(button for button in at.button if button.label == "打开 主报表工作台").click().run()

    assert not at.exception
    assert any(button.label == "返回概览" for button in at.button)
    assert any(button.label == "执行主报表" for button in at.button)
    assert len(at.multiselect) == 1
    assert at.multiselect[0].label == "主报表模块"


def test_gainer_page_uses_calendar_inputs_and_shows_lbma_hint() -> None:
    at = _run_page("gainer")

    assert not at.exception
    date_labels = [widget.label for widget in at.date_input]
    assert "本周末日期（周六）" in date_labels
    assert "两周前日期（周六）" in date_labels
    text_labels = [widget.label for widget in at.text_input]
    assert "本周末黄金价格（USD/oz）" in text_labels
    assert "两周前黄金价格（USD/oz）" in text_labels
    rendered_markdown = "\n".join(markdown.value for markdown in at.markdown)
    assert "LBMA Gold Price" in rendered_markdown
    assert "USD PM" in rendered_markdown


def test_gainer_rejects_non_saturday_dates() -> None:
    at = _run_page("gainer")

    next(widget for widget in at.date_input if widget.label == "本周末日期（周六）").set_value("2026-04-17")
    next(widget for widget in at.date_input if widget.label == "两周前日期（周六）").set_value("2026-04-03")
    next(widget for widget in at.text_input if widget.label == "本周末黄金价格（USD/oz）").set_value("2378.42")
    next(widget for widget in at.text_input if widget.label == "两周前黄金价格（USD/oz）").set_value("2314.15")
    next(button for button in at.button if button.label == "执行 Gainer").click().run()

    assert not at.exception
    assert "必须选择周六" in at.session_state["result"]["output"]


def test_clear_result_keeps_home_visible() -> None:
    at = _run_page()

    next(button for button in at.button if button.label == "清空结果面板").click().run()

    assert not at.exception
    assert any(button.label == "打开 主报表工作台" for button in at.button)
    assert any(button.label == "清空结果面板" for button in at.button)


def test_build_app_config_enables_proxy_by_default() -> None:
    config = build_app_config()

    assert config.use_proxy is True


def test_overall_page_restores_blank_paths_to_defaults() -> None:
    at = AppTest.from_file(APP_FILE)
    at.session_state["active_workspace"] = "overall"
    at.session_state["overall_input_path_text"] = ""
    at.session_state["overall_output_path_text"] = ""
    at.session_state["overall_log_path_text"] = ""

    at.run()

    assert not at.exception
    assert at.session_state["overall_input_path_text"].endswith("data\\seeds\\整体.xlsx")
    assert at.session_state["overall_output_path_text"].endswith("output\\整体_processed.xlsx")
    assert at.session_state["overall_log_path_text"].endswith("output\\raw_data\\整体_calculation_steps.txt")


def test_start_background_job_marks_result_running() -> None:
    streamlit_app._JOB_REGISTRY.clear()
    fake_state = {"active_job_id": None, "result": None}
    original_state = streamlit_app.st.session_state
    streamlit_app.st.session_state = fake_state
    try:
        streamlit_app._start_background_job("测试任务", lambda progress_callback, cancel_check: None)
        assert fake_state["active_job_id"]
        assert fake_state["result"]["status"] == "running"
        job = streamlit_app._get_job(fake_state["active_job_id"])
        assert job is not None
        assert job["state"] in {"running", "success"}
    finally:
        streamlit_app.st.session_state = original_state


def test_request_job_cancel_marks_job_cancelling() -> None:
    streamlit_app._JOB_REGISTRY.clear()
    job_id = "job-test"
    streamlit_app._set_job(job_id, streamlit_app._create_job_payload("主报表"))
    streamlit_app._update_job(job_id, state="running")

    streamlit_app._request_job_cancel(job_id)

    job = streamlit_app._get_job(job_id)
    assert job is not None
    assert job["state"] == "cancelling"
    assert job["cancel_requested"] is True


def test_apply_progress_event_updates_current_unit_and_subtask() -> None:
    streamlit_app._JOB_REGISTRY.clear()
    job_id = "job-progress"
    streamlit_app._set_job(job_id, streamlit_app._create_job_payload("Gainer"))

    streamlit_app._apply_progress_event(
        job_id,
        {
            "event": "step_start",
            "step_label": "步骤 1 / 股票市值",
            "completed_units": [],
            "pending_units": ["步骤 1 / 股票市值", "步骤 2 / 债券市值"],
            "progress_ratio": 0.0,
        },
    )
    streamlit_app._apply_progress_event(
        job_id,
        {
            "event": "subtask_progress",
            "subtask": "S&P 500",
            "progress_label": "S&P 500 120/503",
            "progress_ratio": 0.24,
        },
    )

    job = streamlit_app._get_job(job_id)
    assert job is not None
    assert job["current_unit"] == "步骤 1 / 股票市值"
    assert job["current_subtask"] == "S&P 500"
    assert job["current_subtask_label"] == "S&P 500 120/503"
