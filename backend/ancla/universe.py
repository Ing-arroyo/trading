"""Universo de las diez criptos, con Bitcoin siempre delante."""

from __future__ import annotations

from ancla.cornerstone import ANCHOR_SYMBOL, QUOTE, UNIVERSE_SIZE
from ancla.models import Ticker, UniverseItem

STABLE_BASES = {
    "USDC",
    "FDUSD",
    "TUSD",
    "DAI",
    "USDP",
    "EUR",
    "AEUR",
    "EURI",
    "USDE",
    "USD1",
    "BFUSD",
    "XUSD",
    "USDS",
    "RLUSD",
    "BUSD",
    "USDD",
    "PYUSD",
}
LEVERAGED_TAIL = ("UP", "DOWN", "BULL", "BEAR")


def select_universe(tickers: list[Ticker], quote: str = QUOTE) -> list[UniverseItem]:
    eligible = [ticker for ticker in tickers if _eligible(ticker.symbol, quote)]
    ranked = sorted(eligible, key=lambda ticker: ticker.quote_volume, reverse=True)
    anchor = next((ticker for ticker in ranked if ticker.symbol == ANCHOR_SYMBOL), None)
    if anchor is None:
        return []
    chosen = [
        UniverseItem(
            symbol=anchor.symbol,
            quote_volume=anchor.quote_volume,
            last_price=anchor.last_price,
            anchor=True,
        )
    ]
    for ticker in ranked:
        if ticker.symbol == ANCHOR_SYMBOL:
            continue
        chosen.append(
            UniverseItem(
                symbol=ticker.symbol,
                quote_volume=ticker.quote_volume,
                last_price=ticker.last_price,
            )
        )
        if len(chosen) == UNIVERSE_SIZE:
            break
    return chosen


def _eligible(symbol: str, quote: str) -> bool:
    if not symbol.endswith(quote) or len(symbol) <= len(quote):
        return False
    base = symbol[: -len(quote)]
    if base in STABLE_BASES:
        return False
    if len(base) > 4 and base.endswith(LEVERAGED_TAIL):
        return False
    return base.isalnum()
