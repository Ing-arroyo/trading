"""API local de análisis. No acepta órdenes."""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from ancla import __version__
from ancla.adapters.binance import BinancePublicMarket
from ancla.adapters.demo import DemoMarket
from ancla.cornerstone import BINANCE_SCAN_GAP_SECONDS, EXECUTION_MODE, MAX_CUSTOM_INDICATORS_CAP
from ancla.models import ScanSettings
from ancla.plugins import CATALOG
from ancla.ports import ScanError
from ancla.radar import RadarError, RadarSession, RadarStart, RadarView
from ancla.scanner import scan
from ancla.settings_store import SettingsError, load_settings, project_root, save_settings

app = FastAPI(title="Ancla", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.last_binance = 0.0
app.state.busy = False


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["demo", "binance"] = "demo"
    settings: ScanSettings | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "execution_mode": EXECUTION_MODE, "version": __version__}


@app.get("/api/settings")
def get_settings() -> ScanSettings:
    try:
        return load_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/settings")
def put_settings(settings: ScanSettings) -> ScanSettings:
    return save_settings(settings)


@app.get("/api/plugins/catalog")
def plugin_catalog() -> dict[str, object]:
    return {"cap": MAX_CUSTOM_INDICATORS_CAP, "plugins": CATALOG}


@app.post("/api/scan")
async def run_scan(request: ScanRequest):
    if app.state.busy or _radar_scanning():
        raise HTTPException(status_code=409, detail=_busy_detail())
    settings = request.settings if request.settings is not None else _settings_or_500()
    if request.settings is not None:
        save_settings(settings)
    try:
        return await execute_scan(request.source, settings)
    except ScanError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/radar")
def radar_status() -> RadarView:
    return app.state.radar.view


@app.post("/api/radar/start")
async def radar_start(request: RadarStart) -> RadarView:
    if app.state.radar.view.running:
        raise HTTPException(status_code=409, detail="El radar ya está activo.")
    if app.state.busy:
        raise HTTPException(status_code=409, detail=_busy_detail())
    save_settings(request.settings)
    try:
        return await app.state.radar.start(request)
    except RadarError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/radar/stop")
async def radar_stop() -> RadarView:
    return await app.state.radar.stop()


@app.post("/api/orders")
def orders() -> None:
    raise HTTPException(
        status_code=403,
        detail="La operativa semiautomática en spot no está habilitada en esta versión.",
    )


async def execute_scan(source: str, settings: ScanSettings):
    waited = 0.0
    while app.state.busy:
        await asyncio.sleep(0.2)
        waited += 0.2
        if waited > 40:
            raise ScanError("Ya hay un análisis en curso.")
    app.state.busy = True
    try:
        if source == "binance":
            await _wait_binance_gap()
            timeout = httpx.Timeout(20.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                report = await scan(BinancePublicMarket(client), settings)
            app.state.last_binance = time.monotonic()
            return report
        return await scan(DemoMarket(), settings)
    finally:
        app.state.busy = False


def _radar_scanning() -> bool:
    radar = getattr(app.state, "radar", None)
    return bool(radar is not None and radar.view.running and radar.view.phase == "scanning")


def _busy_detail() -> str:
    radar = getattr(app.state, "radar", None)
    if radar is not None and radar.view.running and radar.view.phase == "scanning":
        return "El radar está leyendo el libro."
    return "Ya hay un análisis en curso."


def _settings_or_500() -> ScanSettings:
    try:
        return load_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_frontend = project_root() / "frontend" / "dist"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="web")


async def _wait_binance_gap() -> None:
    elapsed = time.monotonic() - app.state.last_binance
    if app.state.last_binance and elapsed < BINANCE_SCAN_GAP_SECONDS:
        await asyncio.sleep(BINANCE_SCAN_GAP_SECONDS - elapsed)


app.state.radar = RadarSession(execute_scan)
