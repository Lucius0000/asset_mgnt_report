from streamlit.testing.v1 import AppTest

from src.asset_mgnt_report.config.defaults import build_app_config


APP_FILE = "scripts/web_ui.py"


def _run_page(page: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_FILE)
    if page is not None:
        at.session_state["page"] = page
        at.session_state["nav_page"] = page
    at.run()
    return at


def test_web_ui_home_renders_with_proxy_enabled() -> None:
    at = _run_page()

    assert not at.exception
    assert len(at.checkbox) >= 2
    assert at.checkbox[1].label == "启用代理"
    assert at.checkbox[1].value is True
    assert any(button.label == "进入 主报表工作台" for button in at.button)


def test_build_app_config_enables_proxy_by_default() -> None:
    config = build_app_config()

    assert config.use_proxy is True
