from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from ancla.models import (
    BtcRegime,
    IndicatorReading,
    Reason,
    ScanReport,
    ScanSettings,
    ScoreBreakdown,
    Signal,
    UniverseItem,
)
from ancla.radar import RadarError, RadarSession, RadarStart, RadarView, fresh_names, schedule_error, watch_until
from ancla.api import app


def test_schedule_bounds() -> None:
    assert schedule_error("binance", 30, 60) is not None
    assert schedule_error("demo", 15, 5) is None
    assert schedule_error("binance", 90, 240) is None
    assert schedule_error("demo", 15, 4) is not None


def test_a_pair_is_fresh_until_it_leaves_and_returns() -> None:
    assert fresh_names(set(), ["ETHUSDT"]) == ["ETHUSDT"]
    assert fresh_names({"ETHUSDT"}, ["ETHUSDT", "BTCUSDT"]) == ["BTCUSDT"]
    assert fresh_names({"BTCUSDT"}, ["ETHUSDT"]) == ["ETHUSDT"]


def test_watch_scans_through_the_window_and_logs_each_appearance_once() -> None:
    reports = [
        _report(["ETHUSDT"]),
        _report(["ETHUSDT", "BTCUSDT"]),
        _report(["BTCUSDT"]),
        _report(["ETHUSDT"]),
    ]
    clock = {"t": 0.0}

    async def scan_once() -> ScanReport:
        return reports.pop(0)

    def now() -> float:
        return clock["t"]

    async def sleep(seconds: float) -> None:
        clock["t"] += seconds

    view = RadarView(running=True)

    async def run() -> None:
        await watch_until(
            view,
            window_seconds=35,
            interval_seconds=10,
            scan_once=scan_once,
            now=now,
            sleep=sleep,
            stop=asyncio.Event(),
        )

    asyncio.run(run())
    assert view.scans == 4
    assert view.running is False
    assert view.phase == "finished"
    assert [hit.symbol for hit in view.hits] == ["ETHUSDT", "BTCUSDT", "ETHUSDT"]
    assert [hit.symbol for hit in view.active] == ["ETHUSDT"]


def test_radar_rejects_a_second_start_and_a_short_binance_interval(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANCLA_HOME", str(tmp_path))
    app.state.busy = False
    app.state.last_binance = 0.0

    async def scenario() -> None:
        release = asyncio.Event()

        async def scan_market(source: str, settings: ScanSettings) -> ScanReport:
            del source, settings
            await release.wait()
            return _report(["ETHUSDT"])

        session = RadarSession(scan_market)
        request = RadarStart(
            source="demo",
            interval_seconds=15,
            window_minutes=5,
            settings=ScanSettings(),
        )
        await session.start(request)
        try:
            await session.start(request)
            raise AssertionError("el segundo arranque tenía que fallar")
        except RadarError:
            pass
        release.set()
        await session.stop()

    asyncio.run(scenario())
    client = TestClient(app)
    refused = client.post(
        "/api/radar/start",
        json={
            "source": "binance",
            "interval_seconds": 15,
            "window_minutes": 5,
            "settings": {
                "target_pct": 1,
                "reward_risk": 2,
                "exit_mode": "target",
                "max_custom_indicators": 3,
                "custom_indicators": [],
            },
        },
    )
    assert refused.status_code == 422


def _report(symbols: list[str]) -> ScanReport:
    return ScanReport(
        source="demo",
        execution_mode="analysis_only",
        generated_at="t",
        elapsed_ms=1,
        settings=ScanSettings(),
        btc=BtcRegime(name="bullish", detail="Bitcoin sostiene."),
        universe=[UniverseItem(symbol="BTCUSDT", quote_volume=1, last_price=1, anchor=True)],
        signals=[_signal(symbol) for symbol in symbols],
        rejections=[],
    )


def _signal(symbol: str) -> Signal:
    return Signal(
        symbol=symbol,
        entry=100,
        stop=99.5,
        take_profit=101,
        risk_pct=0.5,
        profit_pct=1,
        reward_risk=2,
        target_pct=1,
        exit_mode="target",
        score=80,
        score_breakdown=ScoreBreakdown(
            base=70, strength=2, proximity=2, imbalance=2, regime=2, room=2, total=80
        ),
        support_low=99.4,
        support_high=99.6,
        support_notional=80_000,
        readings=[IndicatorReading(name="RSI", passed=True, detail="ok")],
        reasons=[Reason(code="qualified", message="ok")],
    )
