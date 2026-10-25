from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from ancla.adapters.binance import BinancePublicMarket
from ancla.api import app
from ancla.ports import ScanError


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("ANCLA_HOME", str(tmp_path))
    app.state.busy = False
    app.state.last_binance = 0.0


def test_health_and_locked_orders() -> None:
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["execution_mode"] == "analysis_only"
    orders = client.post("/api/orders")
    assert orders.status_code == 403


def test_demo_scan_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/api/scan", json={"source": "demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "demo"
    assert any(signal["symbol"] == "ETHUSDT" for signal in body["signals"])
    assert body["signals"][0]["reward_risk"] >= 2


def test_settings_roundtrip_and_plugin_cap() -> None:
    client = TestClient(app)
    catalog = client.get("/api/plugins/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["cap"] == 5
    saved = client.put(
        "/api/settings",
        json={
            "target_pct": 1,
            "reward_risk": 2,
            "exit_mode": "target",
            "max_custom_indicators": 3,
            "custom_indicators": [
                {"kind": "volume_ratio", "params": {"minimum": 1.2}},
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["custom_indicators"][0]["params"]["minimum"] == 1.2
    overloaded = client.put(
        "/api/settings",
        json={
            "target_pct": 1,
            "reward_risk": 2,
            "exit_mode": "target",
            "max_custom_indicators": 1,
            "custom_indicators": [
                {"kind": "rsi_band", "params": {}},
                {"kind": "vwap_side", "params": {}},
            ],
        },
    )
    assert overloaded.status_code == 422


def test_binance_adapter_parses_public_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/ticker/24hr"):
            return httpx.Response(
                200,
                json=[
                    {"symbol": "BTCUSDT", "quoteVolume": "1000", "lastPrice": "60000"},
                    {"symbol": "ETHBTC", "quoteVolume": "5", "lastPrice": "0.05"},
                ],
            )
        if path.endswith("/depth"):
            return httpx.Response(200, json={"bids": [["99", "2"]], "asks": [["101", "1"]]})
        if path.endswith("/klines"):
            return httpx.Response(200, json=[[1_700_000_000_000, "1", "2", "0.5", "1.5", "9"]])
        return httpx.Response(404)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="https://binance.test") as client:
            market = BinancePublicMarket(client, base_url="https://binance.test")
            tickers = await market.tickers("USDT")
            book = await market.depth("BTCUSDT", 100)
            candles = await market.klines("BTCUSDT", "1m", 2)
            assert [ticker.symbol for ticker in tickers] == ["BTCUSDT"]
            assert book.bids[0].price == 99
            assert candles[0].close == 1.5
            with pytest.raises(ScanError):
                await market.depth("bad symbol", 100)

    asyncio.run(run())
