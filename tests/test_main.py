from __future__ import annotations

from scripts import main as main_entry


def test_main_passes_stock_markets_only_to_stock_index(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run_named_pipeline(name: str, **kwargs: object) -> None:
        calls.append((name, kwargs))

    monkeypatch.setattr(main_entry, "run_named_pipeline", fake_run_named_pipeline)

    main_entry.main(
        debug=False,
        modules=["stock_index", "currency"],
        stock_markets=["US"],
    )

    assert calls[0][0] == "stock_index"
    assert calls[0][1]["stock_markets"] == ["US"]
    assert calls[1][0] == "currency"
    assert "stock_markets" not in calls[1][1]
