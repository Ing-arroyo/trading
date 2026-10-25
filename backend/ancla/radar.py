"""Radar: búsquedas globales repetidas, separadas del análisis manual."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ancla.cornerstone import (
    RADAR_HIT_LIMIT,
    RADAR_INTERVAL_DEFAULT,
    RADAR_INTERVAL_MAX,
    RADAR_INTERVAL_MIN_BINANCE,
    RADAR_INTERVAL_MIN_DEMO,
    RADAR_WINDOW_DEFAULT,
    RADAR_WINDOW_MAX,
    RADAR_WINDOW_MIN,
)
from ancla.models import ScanReport, ScanSettings
from ancla.ports import ScanError

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]
Scanner = Callable[[str, ScanSettings], Awaitable[ScanReport]]


class RadarError(RuntimeError):
    pass


class RadarStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["demo", "binance"] = "binance"
    interval_seconds: int = RADAR_INTERVAL_DEFAULT
    window_minutes: int = RADAR_WINDOW_DEFAULT
    settings: ScanSettings

    @model_validator(mode="after")
    def _bounds(self) -> "RadarStart":
        message = schedule_error(self.source, self.interval_seconds, self.window_minutes)
        if message:
            raise ValueError(message)
        return self


class RadarHit(BaseModel):
    detected_at: str
    symbol: str
    entry: float
    stop: float
    take_profit: float
    profit_pct: float
    reward_risk: float
    score: float


class RadarView(BaseModel):
    running: bool = False
    phase: Literal["idle", "scanning", "waiting", "finished"] = "idle"
    source: Literal["demo", "binance"] | None = None
    interval_seconds: int | None = None
    window_minutes: int | None = None
    started_at: str | None = None
    ends_at: str | None = None
    next_scan_at: str | None = None
    last_scan_at: str | None = None
    last_error: str | None = None
    scans: int = 0
    quiet: int = 0
    btc_name: str | None = None
    btc_detail: str | None = None
    universe: list[str] = Field(default_factory=list)
    active: list[RadarHit] = Field(default_factory=list)
    hits: list[RadarHit] = Field(default_factory=list)


def schedule_error(source: str, interval_seconds: int, window_minutes: int) -> str | None:
    minimum = RADAR_INTERVAL_MIN_BINANCE if source == "binance" else RADAR_INTERVAL_MIN_DEMO
    if not minimum <= interval_seconds <= RADAR_INTERVAL_MAX:
        return f"El intervalo debe estar entre {minimum} y {RADAR_INTERVAL_MAX} segundos."
    if not RADAR_WINDOW_MIN <= window_minutes <= RADAR_WINDOW_MAX:
        return f"La ventana debe estar entre {RADAR_WINDOW_MIN} y {RADAR_WINDOW_MAX} minutos."
    return None


def fresh_names(previous: set[str], current: list[str]) -> list[str]:
    """Un par solo vuelve a contar cuando desapareció y reaparece."""
    return [name for name in current if name not in previous]


class RadarSession:
    def __init__(self, scan_market: Scanner) -> None:
        self._scan_market = scan_market
        self.view = RadarView()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self, request: RadarStart) -> RadarView:
        if self.view.running:
            raise RadarError("El radar ya está activo.")
        now = datetime.now(timezone.utc)
        self._stop = asyncio.Event()
        self.view = RadarView(
            running=True,
            phase="scanning",
            source=request.source,
            interval_seconds=request.interval_seconds,
            window_minutes=request.window_minutes,
            started_at=now.isoformat(),
            ends_at=(now + timedelta(minutes=request.window_minutes)).isoformat(),
        )
        self._task = asyncio.create_task(self._run(request))
        return self.view

    async def stop(self) -> RadarView:
        self._stop.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.view.running = False
        self.view.phase = "finished"
        self.view.next_scan_at = None
        return self.view


    async def _run(self, request: RadarStart) -> None:
        try:
            await watch_until(
                self.view,
                window_seconds=request.window_minutes * 60,
                interval_seconds=request.interval_seconds,
                scan_once=lambda: self._scan_market(request.source, request.settings),
                now=asyncio.get_running_loop().time,
                sleep=asyncio.sleep,
                stop=self._stop,
            )
        except asyncio.CancelledError:
            self.view.running = False
            self.view.phase = "finished"
            self.view.next_scan_at = None
            raise


async def watch_until(
    view: RadarView,
    *,
    window_seconds: float,
    interval_seconds: float,
    scan_once: Callable[[], Awaitable[ScanReport]],
    now: Clock,
    sleep: Sleeper,
    stop: asyncio.Event,
) -> None:
    deadline = now() + window_seconds
    seen: set[str] = set()
    try:
        while not stop.is_set() and now() < deadline:
            view.phase = "scanning"
            view.next_scan_at = None
            try:
                report = await scan_once()
            except ScanError as exc:
                view.last_error = str(exc)
            except Exception as exc:
                view.last_error = str(exc) or "La pasada no se pudo completar."
            else:
                _absorb(view, report, seen)
                seen = {signal.symbol for signal in report.signals}
            if stop.is_set() or now() >= deadline:
                break
            view.phase = "waiting"
            view.next_scan_at = (
                datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            ).isoformat()
            if not await _pause(interval_seconds, stop, now, sleep):
                break
    finally:
        view.running = False
        view.phase = "finished"
        view.next_scan_at = None


def _absorb(view: RadarView, report: ScanReport, seen: set[str]) -> None:
    current = [signal.symbol for signal in report.signals]
    appeared = set(fresh_names(seen, current))
    stamp = datetime.now(timezone.utc).isoformat()
    for signal in report.signals:
        if signal.symbol not in appeared:
            continue
        view.hits.insert(0, _hit(signal, stamp))
    view.hits = view.hits[:RADAR_HIT_LIMIT]
    view.active = [_hit(signal, stamp) for signal in report.signals]
    view.scans += 1
    view.quiet = len(report.rejections)
    view.last_scan_at = stamp
    view.last_error = None
    view.btc_name = report.btc.name
    view.btc_detail = report.btc.detail
    view.universe = [item.symbol for item in report.universe]


def _hit(signal, stamp: str) -> RadarHit:
    return RadarHit(
        detected_at=stamp,
        symbol=signal.symbol,
        entry=signal.entry,
        stop=signal.stop,
        take_profit=signal.take_profit,
        profit_pct=signal.profit_pct,
        reward_risk=signal.reward_risk,
        score=signal.score,
    )


async def _pause(total: float, stop: asyncio.Event, now: Clock, sleep: Sleeper) -> bool:
    if total <= 0:
        return not stop.is_set()
    target = now() + total
    while now() < target:
        if stop.is_set():
            return False
        step = min(0.5, target - now())
        if step <= 0:
            break
        await sleep(step)
    return not stop.is_set()
