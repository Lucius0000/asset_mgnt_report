from __future__ import annotations

from datetime import date, datetime
import pandas as pd

from scripts import gainer
from scripts.pipelines import gainer_bond, gainer_stock


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


def test_gainer_main_respects_selected_modules_and_markets(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "Gainer.xlsx"
    original_config = dict(gainer.CONFIG)
    try:
        gainer.CONFIG.update(
            {
                "modules": ["stocks", "btc"],
                "stock_markets": ["US"],
                "current_date": datetime(2026, 4, 11),
                "previous_date": datetime(2026, 3, 28),
                "output_path": output_path,
            }
        )

        monkeypatch.setattr(gainer, "_compute_stock_caps", lambda *args, **kwargs: {"US": {"unit": "USD", "old": 2_000_000_000, "new": 2_250_000_000}})
        monkeypatch.setattr(gainer, "_compute_bond_caps", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bonds should not run")))
        monkeypatch.setattr(gainer, "_compute_gold_caps", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gold should not run")))
        monkeypatch.setattr(gainer, "_compute_btc_caps", lambda *args, **kwargs: (900_000_000_000, 980_000_000_000))
        monkeypatch.setattr(
            "builtins.input",
            lambda _prompt: (_ for _ in ()).throw(AssertionError("input should not be called")),
        )

        gainer.main()

        assert output_path.exists()
        result = pd.read_excel(output_path)
        assert result["资产大类"].fillna("").tolist() == ["股票权益", ""]
        assert result["区域"].tolist() == ["美国", "数字货币（BTC）"]
    finally:
        gainer.CONFIG.clear()
        gainer.CONFIG.update(original_config)


def test_gainer_main_skips_gold_prompt_when_gold_module_not_selected(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "Gainer.xlsx"
    original_config = dict(gainer.CONFIG)
    try:
        gainer.CONFIG.update(
            {
                "modules": ["bonds"],
                "current_date": datetime(2026, 4, 11),
                "previous_date": datetime(2026, 3, 28),
                "output_path": output_path,
            }
        )
        monkeypatch.setattr(
            gainer.gainer_gold,
            "_prompt_price",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gold prompt should not run")),
        )
        monkeypatch.setattr(gainer, "_compute_bond_caps", lambda *args, **kwargs: {"US": {"previous": 10.0, "current": 11.0}, "CN": {"previous": 20.0, "current": 21.0}})
        monkeypatch.setattr(
            "builtins.input",
            lambda _prompt: (_ for _ in ()).throw(AssertionError("input should not be called")),
        )

        gainer.main()

        assert output_path.exists()
    finally:
        gainer.CONFIG.clear()
        gainer.CONFIG.update(original_config)


def test_gainer_related_paths_are_project_root_relative() -> None:
    assert gainer.OUTPUT_PATH == gainer.PROJECT_ROOT / "output" / "Gainer.xlsx"
    assert gainer_bond.DATA_DIR == gainer.PROJECT_ROOT / "data" / "seeds"
    assert gainer_stock.DATA_DIR == gainer.PROJECT_ROOT / "data" / "seeds"
    assert gainer_stock.RAW_DIR == gainer.PROJECT_ROOT / "output" / "raw_data"
