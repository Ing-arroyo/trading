"""Bloques de liquidez a partir del libro visible."""

from __future__ import annotations

import math
from statistics import median

from ancla.cornerstone import (
    BIN_BPS,
    BOOK_WINDOW_BPS,
    IMBALANCE_WINDOW_BPS,
    MIN_WALL_NOTIONAL,
    WALL_MULTIPLIER,
)
from ancla.models import BookView, Level, LiquidityBlock, OrderBook


def read_book(book: OrderBook) -> BookView | None:
    bids = _clean(book.bids, descending=True)
    asks = _clean(book.asks, descending=False)
    if not bids or not asks:
        return None
    best_bid = bids[0].price
    best_ask = asks[0].price
    if best_bid <= 0 or best_ask <= 0:
        return None
    mid = (best_bid + best_ask) / 2
    if mid <= 0:
        return None
    spread_bps = (best_ask - best_bid) / mid * 10_000
    near_bids = _within(bids, mid, IMBALANCE_WINDOW_BPS)
    near_asks = _within(asks, mid, IMBALANCE_WINDOW_BPS)
    bid_notional = sum(level.notional for level in near_bids)
    ask_notional = sum(level.notional for level in near_asks)
    if ask_notional <= 0:
        imbalance = 99.0 if bid_notional > 0 else 0.0
    else:
        imbalance = bid_notional / ask_notional
    window_bids = _within(bids, mid, BOOK_WINDOW_BPS)
    window_asks = _within(asks, mid, BOOK_WINDOW_BPS)
    return BookView(
        best_bid=best_bid,
        best_ask=best_ask,
        mid=mid,
        spread_bps=spread_bps,
        imbalance=imbalance,
        highest_ask=max(level.price for level in asks),
        lowest_bid=min(level.price for level in bids),
        supports=_blocks(window_bids, "bid", mid),
        resistances=_blocks(window_asks, "ask", mid),
    )


def _clean(levels: tuple[Level, ...], *, descending: bool) -> list[Level]:
    valid = [level for level in levels if level.price > 0 and level.quantity > 0]
    return sorted(valid, key=lambda level: level.price, reverse=descending)


def _within(levels: list[Level], mid: float, window_bps: float) -> list[Level]:
    return [
        level
        for level in levels
        if abs(level.price - mid) / mid * 10_000 <= window_bps
    ]


def _blocks(levels: list[Level], side: str, mid: float) -> list[LiquidityBlock]:
    if not levels or mid <= 0:
        return []
    width = mid * BIN_BPS / 10_000
    if width <= 0:
        return []
    bins: dict[int, dict[str, float]] = {}
    for level in levels:
        index = int(math.floor(level.price / width + 1e-8))
        slot = bins.setdefault(
            index,
            {"notional": 0.0, "low": level.price, "high": level.price},
        )
        slot["notional"] += level.notional
        slot["low"] = min(slot["low"], level.price)
        slot["high"] = max(slot["high"], level.price)
    baseline = median(slot["notional"] for slot in bins.values())
    if baseline <= 0:
        return []
    threshold = max(MIN_WALL_NOTIONAL, WALL_MULTIPLIER * baseline)
    wall_indexes = sorted(
        index for index, slot in bins.items() if slot["notional"] >= threshold
    )
    if not wall_indexes:
        return []

    clusters: list[list[int]] = [[wall_indexes[0]]]
    for index in wall_indexes[1:]:
        if index - clusters[-1][-1] <= 1:
            clusters[-1].append(index)
        else:
            clusters.append([index])

    blocks: list[LiquidityBlock] = []
    for cluster in clusters:
        slots = [bins[index] for index in cluster]
        price_low = min(slot["low"] for slot in slots)
        price_high = max(slot["high"] for slot in slots)
        notional = sum(slot["notional"] for slot in slots)
        if side == "bid":
            distance_bps = max(0.0, (mid - price_high) / mid * 10_000)
        else:
            distance_bps = max(0.0, (price_low - mid) / mid * 10_000)
        blocks.append(
            LiquidityBlock(
                side=side,  # type: ignore[arg-type]
                price_low=price_low,
                price_high=price_high,
                notional=notional,
                strength=notional / baseline,
                distance_bps=distance_bps,
            )
        )
    return blocks
