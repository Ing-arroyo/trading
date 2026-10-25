from __future__ import annotations

import pytest

from ancla.indicators import atr, ema, rsi, rolling_vwap, volume_ratio
from ancla.models import ScanSettings, Ticker
from ancla.orderbook import read_book
from ancla.regime import assess_btc
from ancla.risk import plan_exit
from ancla.synthetic import build_book, make_candles
from ancla.universe import select_universe


def test_ema_of_a_flat_series_stays_flat() -> None:
    series = ema([10, 10, 10, 10, 10], 3)
    assert series[-1] == pytest.approx(10)


def test_rsi_of_a_rise_is_overbought() -> None:
    closes = [float(price) for price in range(1, 40)]
    assert rsi(closes, 14) == pytest.approx(100)


def test_universe_pins_bitcoin_and_drops_stables_and_leveraged_tokens() -> None:
    tickers = [
        Ticker(symbol="USDCUSDT", quote_volume=10**12, last_price=1),
        Ticker(symbol="BTCUPUSDT", quote_volume=10**12, last_price=5),
        Ticker(symbol="ETHDOWNUSDT", quote_volume=10**12, last_price=1),
        Ticker(symbol="JUPUSDT", quote_volume=50, last_price=1),
        Ticker(symbol="BTCUSDT", quote_volume=10, last_price=60_000),
    ]
    for index in range(12):
        tickers.append(Ticker(symbol=f"ALT{index}USDT", quote_volume=1_000 - index, last_price=1))
    universe = select_universe(tickers)
    assert [item.symbol for item in universe][0] == "BTCUSDT"
    assert len(universe) == 10
    assert "USDCUSDT" not in {item.symbol for item in universe}
    assert "BTCUPUSDT" not in {item.symbol for item in universe}
    assert "JUPUSDT" not in {item.symbol for item in universe}
    assert select_universe([Ticker(symbol="ETHUSDT", quote_volume=10, last_price=1)]) == []


def test_order_book_finds_a_near_bid_wall_and_a_far_ask_wall() -> None:
    view = read_book(build_book("ETHUSDT", 100))
    assert view is not None
    assert view.spread_bps == pytest.approx(2, abs=0.2)
    assert view.imbalance > 2
    assert len(view.supports) == 1
    assert view.supports[0].price_high == pytest.approx(99.82, rel=0.001)
    assert len(view.resistances) == 1
    assert view.highest_ask > 101


def test_thick_support_is_one_block() -> None:
    view = read_book(build_book("XRPUSDT", 100, bid_offsets_bps=(), thick_support_bins=12))
    assert view is not None
    assert len(view.supports) == 1
    span = view.supports[0].price_high - view.supports[0].price_low
    assert span / 100 > 0.004


def test_equal_book_has_no_wall() -> None:
    view = read_book(build_book("BNBUSDT", 100, bid_offsets_bps=(), ask_offsets_bps=()))
    assert view is not None
    assert view.supports == []
    assert view.resistances == []


def test_target_plan_locks_one_percent_and_at_least_two_to_one() -> None:
    view = read_book(build_book("ETHUSDT", 100))
    assert view is not None
    plan, error = plan_exit(
        view.best_ask,
        view.supports[0],
        view.resistances,
        view.highest_ask,
        ScanSettings(),
    )
    assert error is None
    assert plan is not None
    assert plan.profit_pct == pytest.approx(1, abs=0.001)
    assert plan.reward_risk >= 2


def test_best_rr_extends_the_exit_toward_resistance() -> None:
    view = read_book(build_book("ETHUSDT", 100))
    assert view is not None
    plan, error = plan_exit(
        view.best_ask,
        view.supports[0],
        view.resistances,
        view.highest_ask,
        ScanSettings(exit_mode="best_rr"),
    )
    assert error is None
    assert plan is not None
    assert plan.profit_pct > 1.2
    assert plan.profit_pct <= 2
    assert plan.reward_risk > 2


def test_close_resistance_cancels_the_target() -> None:
    view = read_book(build_book("SOLUSDT", 100, ask_offsets_bps=(40,)))
    assert view is not None
    _plan, error = plan_exit(
        view.best_ask,
        view.supports[0],
        view.resistances,
        view.highest_ask,
        ScanSettings(),
    )
    assert error == "resistance_blocks_target"


def test_wide_support_breaks_the_risk_budget() -> None:
    view = read_book(build_book("XRPUSDT", 100, bid_offsets_bps=(), thick_support_bins=12))
    assert view is not None
    _plan, error = plan_exit(
        view.best_ask,
        view.supports[0],
        view.resistances,
        view.highest_ask,
        ScanSettings(),
    )
    assert error == "risk_exceeds_plan"


def test_bullish_candles_stay_inside_the_entry_band() -> None:
    candles = make_candles(100)
    from ancla.indicators import closes, last_ema

    series = closes(candles)
    fast = last_ema(series, 9)
    slow = last_ema(series, 21)
    value = rsi(series, 14)
    volatility = atr(candles, 14)
    assert fast is not None and slow is not None
    assert fast > slow
    assert series[-1] >= rolling_vwap(candles, 60)
    assert value is not None and 40 <= value <= 66
    assert volatility is not None
    assert 0.03 <= volatility / series[-1] * 100 <= 1.2
    assert volume_ratio(candles, 20) >= 0.75
    regime = assess_btc(candles)
    assert regime.name in {"bullish", "neutral"}


def test_settings_reject_a_loose_or_overloaded_configuration() -> None:
    with pytest.raises(ValueError):
        ScanSettings(target_pct=10)
    with pytest.raises(ValueError):
        ScanSettings(reward_risk=1)
    with pytest.raises(ValueError):
        ScanSettings(
            max_custom_indicators=5,
            custom_indicators=[{"kind": "rsi_band", "params": {}}] * 6,  # type: ignore[list-item]
        )
    with pytest.raises(ValueError):
        ScanSettings(
            custom_indicators=[
                {"kind": "rsi_band", "params": {"min": 70, "max": 40}},  # type: ignore[list-item]
            ]
        )
