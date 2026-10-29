from __future__ import annotations

import asyncio

import pytest

from ancla.models import PluginSpec, ScanSettings
from ancla.ports import AnalysisOnlyBroker, ExecutionLocked, TelegramNotifier
from ancla.regime import assess_btc
from ancla.strategy import evaluate
from ancla.synthetic import build_book, make_candles


def _regime():
    return assess_btc(make_candles(64_000))


def _evaluate(symbol: str = "ETHUSDT", **kwargs):
    price = kwargs.pop("price", 100)
    book = kwargs.pop("book", build_book(symbol, price))
    candles = kwargs.pop("candles", make_candles(price))
    settings = kwargs.pop("settings", ScanSettings())
    regime = kwargs.pop("regime", _regime())
    return evaluate(symbol, book, candles, candles, regime, settings)


def test_cornerstone_emits_a_long_with_the_planned_exit() -> None:
    decision = _evaluate()
    assert decision.accepted, [reason.message for reason in decision.reasons]
    signal = decision.signal
    assert signal is not None
    assert signal.side == "LONG"
    assert signal.profit_pct == pytest.approx(1, abs=0.02)
    assert signal.reward_risk >= 2
    assert signal.score >= 70
    assert signal.stop < signal.entry < signal.take_profit


def test_without_a_bid_wall_indicators_cannot_open_a_trade() -> None:
    decision = _evaluate(book=build_book("BNBUSDT", 100, bid_offsets_bps=(), ask_offsets_bps=()))
    assert not decision.accepted
    assert "no_support" in {reason.code for reason in decision.reasons}


def test_bitcoin_risk_off_stays_visible_and_does_not_block() -> None:
    regime = assess_btc(make_candles(64_000, direction="down"))
    assert regime.name == "risk_off"
    decision = _evaluate(regime=regime)
    assert decision.accepted, [reason.message for reason in decision.reasons]
    assert "btc_regime" not in {reason.code for reason in decision.reasons}
    bitcoin = next(reading for reading in decision.readings if reading.name == "Bitcoin")
    assert bitcoin.passed is False
    assert "contexto" in bitcoin.detail.lower()


def test_custom_indicator_can_veto_and_cannot_replace_the_book() -> None:
    settings = ScanSettings(
        custom_indicators=[PluginSpec(kind="rsi_band", params={"min": 90, "max": 95})]
    )
    decision = _evaluate(settings=settings)
    assert not decision.accepted
    assert any(reason.code == "plugin_rsi_band" for reason in decision.reasons)

    bare = _evaluate(book=build_book("BNBUSDT", 100, bid_offsets_bps=(), ask_offsets_bps=()), settings=settings)
    assert not bare.accepted
    assert "no_support" in {reason.code for reason in bare.reasons}


def test_locked_ports_refuse_orders_and_telegram() -> None:
    signal = _evaluate().signal
    assert signal is not None
    with pytest.raises(ExecutionLocked):
        AnalysisOnlyBroker().submit(signal)
    with pytest.raises(ExecutionLocked):
        TelegramNotifier().send("entrada")


def test_demo_scan_separates_signals_from_specific_rejections() -> None:
    from ancla.adapters.demo import DemoMarket
    from ancla.scanner import scan

    report = asyncio.run(scan(DemoMarket(), ScanSettings()))
    assert report.execution_mode == "analysis_only"
    assert report.universe[0].symbol == "BTCUSDT"
    assert len(report.universe) == 10
    accepted = {signal.symbol for signal in report.signals}
    assert {"BTCUSDT", "ETHUSDT"} <= accepted
    reasons = {item.symbol: {reason.code for reason in item.reasons} for item in report.rejections}
    assert "no_support" in reasons["BNBUSDT"]
    assert "resistance_blocks_target" in reasons["SOLUSDT"]
    assert "risk_exceeds_plan" in reasons["XRPUSDT"]
    assert "spread" in reasons["DOGEUSDT"]
    assert "btc_regime" not in reasons["ADAUSDT"]
    assert "trend_5m" in reasons["ADAUSDT"] or "trend_1m" in reasons["ADAUSDT"]
    assert "volume" in reasons["LINKUSDT"]
    assert "atr" in reasons["LTCUSDT"]
    assert "imbalance" in reasons["AVAXUSDT"] or "resistance_blocks_target" in reasons["AVAXUSDT"]
