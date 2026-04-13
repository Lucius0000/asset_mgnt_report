from streamlit.testing.v1 import AppTest

from src.asset_mgnt_report.config.defaults import build_app_config


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


def test_clear_result_keeps_home_visible() -> None:
    at = _run_page()

    next(button for button in at.button if button.label == "清空结果面板").click().run()

    assert not at.exception
    assert any(button.label == "打开 主报表工作台" for button in at.button)
    assert any(button.label == "清空结果面板" for button in at.button)


def test_build_app_config_enables_proxy_by_default() -> None:
    config = build_app_config()

    assert config.use_proxy is True
