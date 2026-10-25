"""Fronteras de la aplicación.

El mercado se lee. El bróker y Telegram existen como contrato y, en esta
versión, rechazan cualquier intento de operar o de avisar.
"""

from __future__ import annotations

from typing import Protocol

from ancla.models import Candle, OrderBook, Signal, Ticker


class ScanError(RuntimeError):
    pass


class ExecutionLocked(RuntimeError):
    pass


class MarketDataPort(Protocol):
    name: str

    async def tickers(self, quote: str) -> list[Ticker]:
        ...

    async def depth(self, symbol: str, limit: int) -> OrderBook:
        ...

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        ...


class BrokerPort(Protocol):
    def submit(self, signal: Signal) -> None:
        ...


class NotifierPort(Protocol):
    def send(self, text: str) -> None:
        ...


class AnalysisOnlyBroker:
    """Reservado para Binance Spot. Esta versión no firma ni envía órdenes."""

    mode = "analysis_only"

    def submit(self, signal: Signal) -> None:
        del signal
        raise ExecutionLocked(
            "La operativa semiautomática en spot no está habilitada en esta versión."
        )


class TelegramNotifier:
    """Reservado para avisos. Esta versión no abre conexión con Telegram."""

    enabled = False

    def send(self, text: str) -> None:
        del text
        raise ExecutionLocked(
            "Las notificaciones de Telegram no están habilitadas en esta versión."
        )
