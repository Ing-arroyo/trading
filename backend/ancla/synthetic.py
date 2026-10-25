"""Series y libros sintéticos para el modo demo y las pruebas."""

from __future__ import annotations

from ancla.models import Candle, Level, OrderBook


def make_candles(
    start: float,
    *,
    direction: str = "up",
    count: int = 103,
    range_pct: float = 0.08,
    volume: float = 20.0,
    dry_last: bool = False,
) -> list[Candle]:
    if direction not in {"up", "down"}:
        raise ValueError("direction debe ser 'up' o 'down'.")
    sign = 1 if direction == "up" else -1
    # Subida bastante limpia y luego un respiro. El respiro mete el RSI
    # en la banda de scalping sin dar la vuelta a las medias.
    steps = [0.0014] * 55 + [-0.00055, 0.00035, -0.0004, 0.0003, -0.00025, 0.0004] * 8
    if count != len(steps):
        steps = (steps * ((count // len(steps)) + 1))[:count]
    closes: list[float] = []
    price = start
    for step in steps:
        price *= 1 + sign * step
        closes.append(price)

    candles: list[Candle] = []
    previous = start
    for index, close in enumerate(closes):
        half = close * (range_pct / 100)
        high = max(previous, close) + half
        low = min(previous, close) - half
        bar_volume = volume * (0.05 if dry_last and index == count - 1 else 1)
        candles.append(
            Candle(
                open_time=1_700_000_000_000 + index * 60_000,
                open=previous,
                high=high,
                low=max(low, 0.00000001),
                close=close,
                volume=bar_volume,
            )
        )
        previous = close
    return candles


def build_book(
    symbol: str,
    mid: float,
    *,
    bid_offsets_bps: tuple[float, ...] = (-18,),
    ask_offsets_bps: tuple[float, ...] = (150,),
    wall_notional: float = 80_000,
    spread_bps: float = 2,
    step_bps: float = 8,
    depth: int = 40,
    tiny_notional: float = 800,
    thick_support_bins: int = 0,
) -> OrderBook:
    """Libro con escalones chicos y muros opcionales, en puntos básicos desde el medio."""
    half = spread_bps / 2
    best_bid = mid * (1 - half / 10_000)
    best_ask = mid * (1 + half / 10_000)
    bids = [_level(best_bid, tiny_notional)]
    asks = [_level(best_ask, tiny_notional)]
    bid_price = best_bid
    ask_price = best_ask
    for _ in range(depth):
        bid_price *= 1 - step_bps / 10_000
        ask_price *= 1 + step_bps / 10_000
        bids.append(_level(bid_price, tiny_notional))
        asks.append(_level(ask_price, tiny_notional))
    for offset in bid_offsets_bps:
        bids.append(_level(mid * (1 + offset / 10_000), wall_notional))
    width = mid * 5 / 10_000
    if thick_support_bins:
        start = mid * (1 - 15 / 10_000)
        for index in range(thick_support_bins):
            bids.append(_level(start - index * width, wall_notional))
    for offset in ask_offsets_bps:
        asks.append(_level(mid * (1 + offset / 10_000), wall_notional))
    return OrderBook(symbol=symbol, bids=tuple(bids), asks=tuple(asks))


def _level(price: float, notional: float) -> Level:
    return Level(price=price, quantity=notional / price)
