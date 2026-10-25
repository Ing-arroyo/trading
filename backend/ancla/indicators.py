"""Indicadores puros. Sin red y sin estado."""

from __future__ import annotations

from ancla.models import Candle


def ema(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("El periodo de la EMA tiene que ser positivo.")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    multiplier = 2 / (period + 1)
    previous = seed
    for index in range(period, len(values)):
        previous = values[index] * multiplier + previous * (1 - multiplier)
        out[index] = previous
    return out


def last_ema(values: list[float], period: int) -> float | None:
    series = ema(values, period)
    return series[-1] if series else None


def rsi(closes: list[float], period: int = 14) -> float | None:
    if period < 1 or len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
    if average_loss == 0:
        return 100.0
    relative = average_gain / average_loss
    return 100 - (100 / (1 + relative))


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if period < 1 or len(candles) < period:
        return None
    true_ranges: list[float] = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)
    average = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        average = (average * (period - 1) + true_range) / period
    return average


def rolling_vwap(candles: list[Candle], window: int = 60) -> float | None:
    if window < 1 or not candles:
        return None
    chunk = candles[-window:]
    volume = sum(candle.volume for candle in chunk)
    if volume <= 0:
        return None
    weighted = sum(_typical(candle) * candle.volume for candle in chunk)
    return weighted / volume


def volume_ratio(candles: list[Candle], window: int = 20) -> float | None:
    if len(candles) < window:
        return None
    baseline = sum(candle.volume for candle in candles[-window:]) / window
    if baseline <= 0:
        return None
    return candles[-1].volume / baseline


def closes(candles: list[Candle]) -> list[float]:
    return [candle.close for candle in candles]


def _typical(candle: Candle) -> float:
    return (candle.high + candle.low + candle.close) / 3
