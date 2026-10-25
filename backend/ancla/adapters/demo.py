"""Mercado determinista. Mismos códigos de decisión que un libro real."""

from __future__ import annotations

from ancla.models import Candle, OrderBook, Ticker
from ancla.synthetic import build_book, make_candles

_PRICES = {
    "BTCUSDT": 64_000,
    "ETHUSDT": 3_200,
    "SOLUSDT": 150,
    "BNBUSDT": 600,
    "XRPUSDT": 0.55,
    "ADAUSDT": 0.4,
    "DOGEUSDT": 0.12,
    "AVAXUSDT": 28,
    "LINKUSDT": 14,
    "LTCUSDT": 70,
}


class DemoMarket:
    name = "demo"

    async def tickers(self, quote: str) -> list[Ticker]:
        del quote
        rows = [
            Ticker(symbol=symbol, quote_volume=1_000_000_000 - index * 10_000_000, last_price=price)
            for index, (symbol, price) in enumerate(_PRICES.items())
        ]
        rows.extend(
            [
                Ticker(symbol="USDCUSDT", quote_volume=9e12, last_price=1),
                Ticker(symbol="BTCUPUSDT", quote_volume=9e12, last_price=20),
                Ticker(symbol="ETHDOWNUSDT", quote_volume=9e12, last_price=0.1),
                Ticker(symbol="JUPUSDT", quote_volume=1, last_price=1),
            ]
        )
        return rows

    async def depth(self, symbol: str, limit: int) -> OrderBook:
        del limit
        price = _PRICES[symbol]
        if symbol == "BNBUSDT":
            return build_book(symbol, price, bid_offsets_bps=(), ask_offsets_bps=())
        if symbol == "XRPUSDT":
            return build_book(
                symbol,
                price,
                bid_offsets_bps=(),
                ask_offsets_bps=(150,),
                thick_support_bins=12,
            )
        if symbol == "SOLUSDT":
            return build_book(symbol, price, ask_offsets_bps=(40,))
        if symbol == "DOGEUSDT":
            return build_book(symbol, price, spread_bps=80)
        if symbol == "AVAXUSDT":
            return build_book(symbol, price, ask_offsets_bps=(15,))
        return build_book(symbol, price)

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        del interval
        price = _PRICES[symbol]
        if symbol == "ADAUSDT":
            candles = make_candles(price, direction="down")
        elif symbol == "LTCUSDT":
            candles = make_candles(price, range_pct=1.8)
        elif symbol == "LINKUSDT":
            candles = make_candles(price, dry_last=True)
        else:
            candles = make_candles(price)
        return candles[-limit:]
