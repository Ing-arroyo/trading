"""Orquesta un análisis. Si Bitcoin no se puede leer, no hay análisis."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from ancla.cornerstone import (
    ANCHOR_SYMBOL,
    DEPTH_LIMIT,
    EXECUTION_MODE,
    KLINE_LIMIT,
    QUOTE,
    SCALP_INTERVAL,
    TREND_INTERVAL,
)
from ancla.models import Reason, ScanReport, ScanSettings, SymbolDecision, UniverseItem
from ancla.ports import MarketDataPort, ScanError
from ancla.regime import assess_btc
from ancla.strategy import evaluate
from ancla.universe import select_universe


async def scan(market: MarketDataPort, settings: ScanSettings) -> ScanReport:
    started = time.perf_counter()
    tickers = await market.tickers(QUOTE)
    universe = select_universe(tickers)
    if not any(item.symbol == ANCHOR_SYMBOL for item in universe):
        raise ScanError("El universo no incluye BTCUSDT. Sin Bitcoin no hay análisis.")

    snapshots: list[tuple[UniverseItem, object, object, object]] = []
    early_rejections: list[SymbolDecision] = []
    for item in universe:
        try:
            book = await market.depth(item.symbol, DEPTH_LIMIT)
            candles_1m = await market.klines(item.symbol, SCALP_INTERVAL, KLINE_LIMIT)
            candles_5m = await market.klines(item.symbol, TREND_INTERVAL, KLINE_LIMIT)
        except ScanError:
            if item.symbol == ANCHOR_SYMBOL:
                raise ScanError("No se pudo leer Bitcoin. El análisis se detiene.") from None
            early_rejections.append(
                SymbolDecision(
                    symbol=item.symbol,
                    accepted=False,
                    reasons=[
                        Reason(
                            code="market_data",
                            message="No se pudo leer el libro o las velas de este par.",
                        )
                    ],
                    readings=[],
                )
            )
            continue
        snapshots.append((item, book, candles_1m, candles_5m))

    anchor = next((snap for snap in snapshots if snap[0].symbol == ANCHOR_SYMBOL), None)
    if anchor is None:
        raise ScanError("No se pudo leer Bitcoin. El análisis se detiene.")
    regime = assess_btc(anchor[3])  # type: ignore[arg-type]

    signals = []
    rejections = list(early_rejections)
    for item, book, candles_1m, candles_5m in snapshots:
        decision = evaluate(item.symbol, book, candles_1m, candles_5m, regime, settings)  # type: ignore[arg-type]
        if decision.accepted and decision.signal is not None:
            signals.append(decision.signal)
        else:
            rejections.append(decision)
    signals.sort(key=lambda signal: signal.score, reverse=True)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ScanReport(
        source=market.name,
        execution_mode=EXECUTION_MODE,
        generated_at=datetime.now(timezone.utc).isoformat(),
        elapsed_ms=elapsed_ms,
        settings=settings,
        btc=regime,
        universe=universe,
        signals=signals,
        rejections=rejections,
    )
