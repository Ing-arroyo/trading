"""Régimen de Bitcoin. Se muestra en cada análisis y no veta candidatos."""

from __future__ import annotations

from ancla.cornerstone import (
    BTC_RETURN_CANDLES,
    BTC_SHOCK_RETURN_PCT,
    EMA_FAST,
    EMA_SLOW,
    MIN_CANDLES,
)
from ancla.indicators import closes, last_ema
from ancla.models import BtcRegime, Candle


def assess_btc(candles: list[Candle]) -> BtcRegime:
    if len(candles) < MIN_CANDLES:
        return BtcRegime(
            name="unknown",
            detail="No hay suficientes velas de 5m de Bitcoin para fijar el régimen.",
        )
    series = closes(candles)
    fast = last_ema(series, EMA_FAST)
    slow = last_ema(series, EMA_SLOW)
    close = series[-1]
    previous = series[-(BTC_RETURN_CANDLES + 1)]
    return_pct = (close - previous) / previous * 100 if previous else 0.0
    if fast is None or slow is None:
        return BtcRegime(name="unknown", detail="No se pudo calcular la tendencia de Bitcoin.")

    bearish_stack = close < slow and fast < slow
    shock = return_pct <= BTC_SHOCK_RETURN_PCT
    if bearish_stack or shock:
        cause = "Bitcoin cae con las medias en contra." if bearish_stack else "Bitcoin acaba de ceder con fuerza."
        return BtcRegime(
            name="risk_off",
            detail=f"{cause} Es contexto: no impide una entrada que cumpla el resto.",
            return_pct=return_pct,
            close=close,
            ema_fast=fast,
            ema_slow=slow,
        )
    if close > slow and fast > slow and return_pct > -0.15:
        return BtcRegime(
            name="bullish",
            detail="Bitcoin sostiene la tendencia alcista de 5m.",
            return_pct=return_pct,
            close=close,
            ema_fast=fast,
            ema_slow=slow,
        )
    return BtcRegime(
        name="neutral",
        detail="Bitcoin no confirma tendencia. La entrada depende del libro y del resto de indicadores.",
        return_pct=return_pct,
        close=close,
        ema_fast=fast,
        ema_slow=slow,
    )
