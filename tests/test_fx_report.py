from __future__ import annotations

import os

import pandas as pd

from scripts.pipelines import fx_report


def test_calculate_metrics_handles_empty_frames_without_crashing() -> None:
    metrics = fx_report.calculate_metrics(
        {
            "USD_CNH": pd.DataFrame(columns=["日期", "汇率"]),
            "USD_HKD": pd.DataFrame(columns=["日期", "汇率"]),
        }
    )

    assert len(metrics) == 2
    assert metrics["汇率值"].isna().all()
    assert metrics["MoM(%)"].isna().all()
    assert metrics["YoY(%)"].isna().all()


def test_get_fx_data_retries_without_proxy_on_proxy_failure(monkeypatch) -> None:
    calls: list[str] = []
    original_http_proxy = os.environ.get("http_proxy")
    original_https_proxy = os.environ.get("https_proxy")
    os.environ["http_proxy"] = "http://127.0.0.1:7890"
    os.environ["https_proxy"] = "http://127.0.0.1:7890"

    def fake_forex_hist_em(*, symbol: str):
        calls.append(os.environ.get("http_proxy", ""))
        if len(calls) == 1:
            raise RuntimeError("ProxyError: Unable to connect to proxy")
        return pd.DataFrame(
            {
                "日期": ["2026-04-10", "2026-04-11"],
                "最新价": [7.23, 7.25],
            }
        )

    monkeypatch.setattr(fx_report.ak, "forex_hist_em", fake_forex_hist_em)

    try:
        result = fx_report.get_fx_data("USDCNH")
    finally:
        if original_http_proxy is None:
            os.environ.pop("http_proxy", None)
        else:
            os.environ["http_proxy"] = original_http_proxy
        if original_https_proxy is None:
            os.environ.pop("https_proxy", None)
        else:
            os.environ["https_proxy"] = original_https_proxy

    assert len(calls) == 2
    assert calls[0] == "http://127.0.0.1:7890"
    assert calls[1] == ""
    assert not result.empty
    assert list(result.columns) == ["日期", "汇率"]
    assert result.attrs["data_source"] == "forex_hist_em"


def test_yfinance_fallback_uses_proxy_and_marks_source(monkeypatch) -> None:
    calls: list[str | None] = []
    original_http_proxy = os.environ.get("http_proxy")
    os.environ["http_proxy"] = "http://127.0.0.1:7890"

    def fake_download(*args, **kwargs):
        calls.append(kwargs.get("proxy"))
        dates = pd.to_datetime(["2025-04-11", "2026-03-13", "2026-04-11"])
        return pd.DataFrame({"Close": [7.01, 7.21, 7.22]}, index=dates)

    monkeypatch.setattr(fx_report.yf, "download", fake_download)

    try:
        result = fx_report._get_fx_data_yfinance("USDCNH")
    finally:
        if original_http_proxy is None:
            os.environ.pop("http_proxy", None)
        else:
            os.environ["http_proxy"] = original_http_proxy

    assert calls == ["http://127.0.0.1:7890"]
    assert not result.empty
    assert result.attrs["data_source"] == "yfinance"


def test_yfinance_fallback_uses_official_source_when_history_is_too_short(monkeypatch) -> None:
    def fake_download(*args, **kwargs):
        return pd.DataFrame({"Close": [7.22]}, index=pd.to_datetime(["2026-04-11"]))

    fallback = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2025-04-11", "2026-03-13", "2026-04-11"]),
            "汇率": [7.02, 7.20, 7.22],
        }
    )
    fallback.attrs["data_source"] = "currency_boc_safe"

    monkeypatch.setattr(fx_report.yf, "download", fake_download)
    monkeypatch.setattr(fx_report, "_get_fx_data_official", lambda symbol_code: fallback.copy())

    result = fx_report._get_fx_data_yfinance("USDCNH")

    assert result.attrs["data_source"] == "currency_boc_safe"
    assert len(result) == 3


def test_harmonize_pair_sources_prefers_common_fallback(monkeypatch) -> None:
    usd_cnh = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2025-04-11", "2026-03-13", "2026-04-11"]),
            "汇率": [7.02, 7.20, 7.22],
        }
    )
    usd_cnh.attrs["data_source"] = "yfinance"

    usd_hkd = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2025-04-11", "2026-03-13", "2026-04-11"]),
            "汇率": [7.75, 7.82, 7.83],
        }
    )
    usd_hkd.attrs["data_source"] = "currency_boc_safe"

    safe_usd_cnh = usd_cnh.copy()
    safe_usd_cnh.attrs["data_source"] = "currency_boc_safe"
    safe_usd_hkd = usd_hkd.copy()
    safe_usd_hkd.attrs["data_source"] = "currency_boc_safe"

    monkeypatch.setattr(fx_report, "_get_fx_data_boc_safe", lambda symbol: safe_usd_cnh.copy() if symbol == "USDCNH" else safe_usd_hkd.copy())
    monkeypatch.setattr(fx_report, "_get_fx_data_yfinance", lambda symbol: pd.DataFrame(columns=["日期", "汇率"]))
    monkeypatch.setattr(fx_report, "_get_fx_data_boc_sina", lambda symbol: pd.DataFrame(columns=["日期", "汇率"]))
    monkeypatch.setattr(fx_report, "_load_cached_fx_data", lambda symbol: pd.DataFrame(columns=["日期", "汇率"]))

    result = fx_report._harmonize_pair_sources({"USD_CNH": usd_cnh, "USD_HKD": usd_hkd})

    assert result["USD_CNH"].attrs["data_source"] == "currency_boc_safe"
    assert result["USD_HKD"].attrs["data_source"] == "currency_boc_safe"
