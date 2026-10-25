"""Lectura pública de Binance. Sin clave y sin firma."""

from __future__ import annotations

import asyncio
import re
import time

import httpx

from ancla.models import Candle, Level, OrderBook, Ticker
from ancla.ports import ScanError

_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")
_INTERVALS = {"1m", "5m"}
_DEPTHS = {5, 10, 20, 50, 100, 500, 1000, 5000}
# El dominio principal bloquea con 451 a los servidores de algunas regiones.
# El de datos públicos responde el mismo libro y las mismas velas.
_PUBLIC_HOSTS = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
)


class BinancePublicMarket:
    name = "binance"

    def __init__(self, client: httpx.AsyncClient, base_url: str | None = None) -> None:
        self._client = client
        self._hosts = (base_url.rstrip("/"),) if base_url else _PUBLIC_HOSTS
        self._host_index = 0
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def tickers(self, quote: str) -> list[Ticker]:
        payload = await self._get("/api/v3/ticker/24hr")
        if not isinstance(payload, list):
            raise ScanError("Binance devolvió un listado de precios ilegible.")
        tickers: list[Ticker] = []
        for row in payload:
            ticker = _ticker(row)
            if ticker is not None and ticker.symbol.endswith(quote):
                tickers.append(ticker)
        if not tickers:
            raise ScanError("Binance no devolvió pares cotizados en USDT.")
        return tickers

    async def depth(self, symbol: str, limit: int) -> OrderBook:
        _check_symbol(symbol)
        if limit not in _DEPTHS:
            raise ScanError("El límite de profundidad no es válido.")
        payload = await self._get("/api/v3/depth", {"symbol": symbol, "limit": limit})
        try:
            bids = tuple(_level(row) for row in payload["bids"])
            asks = tuple(_level(row) for row in payload["asks"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ScanError(f"Libro ilegible para {symbol}.") from exc
        if not bids or not asks:
            raise ScanError(f"Libro vacío para {symbol}.")
        return OrderBook(symbol=symbol, bids=bids, asks=asks)

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        _check_symbol(symbol)
        if interval not in _INTERVALS:
            raise ScanError("El intervalo de velas no es válido.")
        payload = await self._get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list):
            raise ScanError(f"Velas ilegibles para {symbol}.")
        try:
            return [_candle(row) for row in payload]
        except (IndexError, TypeError, ValueError) as exc:
            raise ScanError(f"Velas ilegibles para {symbol}.") from exc

    async def _get(self, path: str, params: dict | None = None) -> object:
        last_error = "Binance no respondió."
        for attempt in range(4):
            async with self._lock:
                wait = 0.05 - (time.monotonic() - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    response = await self._client.get(f"{self._host()}{path}", params=params)
                except httpx.HTTPError as exc:
                    last_error = "No hay conexión con Binance."
                    self._last_call = time.monotonic()
                    response = None
                    error = exc
                else:
                    error = None
                    self._last_call = time.monotonic()
            if error is not None:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            assert response is not None
            if response.status_code == 451 and self._host_index + 1 < len(self._hosts):
                self._host_index += 1
                continue
            if response.status_code in {418, 429, 500, 503}:
                last_error = "Binance está limitando las consultas. Espera unos segundos."
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code == 451:
                raise ScanError(
                    "Binance bloqueó la consulta por la región del servidor. "
                    "Tampoco respondió el espejo de datos públicos."
                )
            if response.status_code >= 400:
                raise ScanError(f"Binance rechazó la consulta ({response.status_code}).")
            try:
                return response.json()
            except ValueError as exc:
                raise ScanError("Binance devolvió una respuesta que no es JSON.") from exc
        raise ScanError(last_error)

    def _host(self) -> str:
        return self._hosts[self._host_index]


def _check_symbol(symbol: str) -> None:
    if _SYMBOL.fullmatch(symbol) is None:
        raise ScanError("Símbolo de mercado no válido.")


def _ticker(row: object) -> Ticker | None:
    if not isinstance(row, dict):
        return None
    try:
        return Ticker(
            symbol=str(row["symbol"]),
            quote_volume=float(row["quoteVolume"]),
            last_price=float(row["lastPrice"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _level(row: object) -> Level:
    if not isinstance(row, (list, tuple)) or len(row) < 2:
        raise ValueError("nivel")
    price = float(row[0])
    quantity = float(row[1])
    if price <= 0 or quantity <= 0:
        raise ValueError("nivel")
    return Level(price=price, quantity=quantity)


def _candle(row: object) -> Candle:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        raise ValueError("vela")
    return Candle(
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
