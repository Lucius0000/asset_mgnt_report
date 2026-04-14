from __future__ import annotations

from datetime import date, datetime

from scripts import gainer


def test_default_current_saturday_uses_previous_saturday_before_friday() -> None:
    assert gainer.default_current_saturday(date(2026, 4, 14)) == datetime(2026, 4, 11)
    assert gainer.default_current_saturday(date(2026, 4, 16)) == datetime(2026, 4, 11)


def test_default_current_saturday_uses_current_week_saturday_from_friday() -> None:
    assert gainer.default_current_saturday(date(2026, 4, 17)) == datetime(2026, 4, 18)
    assert gainer.default_current_saturday(date(2026, 4, 18)) == datetime(2026, 4, 18)
    assert gainer.default_current_saturday(date(2026, 4, 19)) == datetime(2026, 4, 18)


def test_default_gainer_dates_are_two_weeks_apart() -> None:
    current, previous = gainer.default_gainer_dates(date(2026, 4, 14))

    assert current == datetime(2026, 4, 11)
    assert previous == datetime(2026, 3, 28)
    assert (current - previous).days == 14


def test_prompt_date_accepts_blank_input_and_uses_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _message: "")

    result = gainer._prompt_date(
        "请输入本周末日期（YYYY-MM-DD，周六），回车默认 2026-04-11:",
        default=datetime(2026, 4, 11),
    )

    assert result == datetime(2026, 4, 11)


def test_prompt_date_normalizes_explicit_date_without_prompt(monkeypatch) -> None:
    original_config = dict(gainer.CONFIG)
    try:
        gainer.CONFIG["current_date"] = date(2026, 4, 18)
        monkeypatch.setattr(
            "builtins.input",
            lambda _message: (_ for _ in ()).throw(AssertionError("input should not be called")),
        )

        result = gainer._prompt_date(
            "请输入本周末日期（YYYY-MM-DD，周六），回车默认 2026-04-18:",
            default=datetime(2026, 4, 18),
        )

        assert result == datetime(2026, 4, 18)
    finally:
        gainer.CONFIG.clear()
        gainer.CONFIG.update(original_config)
