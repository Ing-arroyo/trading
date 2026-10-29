"""Confluencia de la estrategia principal.

Todas las compuertas son obligatorias. El puntaje solo ordena las que ya pasaron.
"""

from __future__ import annotations

from ancla.cornerstone import (
    ATR_PCT_MAX,
    ATR_PCT_MIN,
    ATR_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    MAX_SPREAD_BPS,
    MIN_CANDLES,
    MIN_IMBALANCE,
    MIN_SCORE,
    MIN_VOLUME_RATIO,
    PROXIMITY_BPS,
    RSI_MAX,
    RSI_MIN,
    RSI_PERIOD,
    SCORE_CAP,
    VOLUME_AVG,
    VWAP_WINDOW,
    WALL_MULTIPLIER,
)
from ancla.indicators import atr, closes, last_ema, rolling_vwap, rsi, volume_ratio
from ancla.models import (
    BtcRegime,
    Candle,
    IndicatorReading,
    OrderBook,
    Reason,
    ScanSettings,
    ScoreBreakdown,
    Signal,
    SymbolDecision,
)
from ancla.orderbook import read_book
from ancla.plugins import evaluate_plugin
from ancla.risk import plan_exit, supports_in_range

_MESSAGES = {
    "empty_book": "El libro no tiene puntas utilizables.",
    "crossed_book": "El libro está cruzado.",
    "insufficient_candles": "No hay suficientes velas para los indicadores.",
    "spread": "El spread es demasiado ancho para un scalp.",
    "no_support": "No hay un bloque de soporte a distancia de entrada.",
    "imbalance": "El libro cercano no acompaña al comprador.",
    "trend_5m": "La tendencia de 5m no acompaña el largo.",
    "trend_1m": "La tendencia de 1m no acompaña el largo.",
    "vwap": "El precio está debajo del VWAP.",
    "rsi": "El RSI de 1m está fuera de la banda de entrada.",
    "atr": "La volatilidad de 1m no sirve para este scalp.",
    "volume": "La última vela no tiene volumen suficiente.",
    "book_does_not_cover_target": "El libro visible no llega hasta el objetivo.",
    "resistance_blocks_target": "Un bloque de resistencia impide la ganancia pedida.",
    "risk_exceeds_plan": "El soporte obliga a arriesgar más de lo que permite la relación.",
    "reward_too_small": "La salida no cumple ganancia y relación beneficio/riesgo.",
}


def evaluate(
    symbol: str,
    book: OrderBook,
    candles_1m: list[Candle],
    candles_5m: list[Candle],
    regime: BtcRegime,
    settings: ScanSettings,
) -> SymbolDecision:
    if len(candles_1m) < MIN_CANDLES or len(candles_5m) < MIN_CANDLES:
        return _decision(symbol, [_reason("insufficient_candles")], [])

    view = read_book(book)
    if view is None:
        return _decision(symbol, [_reason("empty_book")], [])
    if view.best_ask <= view.best_bid:
        return _decision(symbol, [_reason("crossed_book")], [])

    entry = view.best_ask
    reasons: list[Reason] = []
    readings: list[IndicatorReading] = []

    spread_ok = 0 <= view.spread_bps <= MAX_SPREAD_BPS
    readings.append(
        IndicatorReading(
            name="Spread",
            passed=spread_ok,
            detail=f"{view.spread_bps:.1f} bps.",
        )
    )
    if not spread_ok:
        reasons.append(_reason("spread"))

    candidates = supports_in_range(view.supports, entry)
    if not candidates:
        reasons.append(_reason("no_support"))
        plan = None
        plan_error = "no_support"
    else:
        viable = []
        errors: list[tuple[float, str]] = []
        for block in candidates:
            distance = _distance(entry, block.price_high)
            planned, error = plan_exit(
                entry,
                block,
                view.resistances,
                view.highest_ask,
                settings,
            )
            if planned is not None:
                viable.append(planned)
            elif error is not None:
                errors.append((distance, error))
        if viable:
            plan = max(viable, key=lambda item: (item.reward_risk, item.support.strength))
            plan_error = None
        else:
            plan = None
            plan_error = sorted(errors, key=lambda item: item[0])[0][1]
            reasons.append(_reason(plan_error))

    imbalance_ok = view.imbalance >= MIN_IMBALANCE
    readings.append(
        IndicatorReading(
            name="Desequilibrio",
            passed=imbalance_ok,
            detail=f"Compras/ventas cercanas {view.imbalance:.2f}.",
        )
    )
    if not imbalance_ok:
        reasons.append(_reason("imbalance"))

    readings.append(
        IndicatorReading(
            name="Bitcoin",
            passed=regime.name == "bullish",
            detail=regime.detail,
        )
    )

    close_1m = closes(candles_1m)
    close_5m = closes(candles_5m)
    fast_5 = last_ema(close_5m, EMA_FAST)
    slow_5 = last_ema(close_5m, EMA_SLOW)
    trend_5_ok = (
        fast_5 is not None
        and slow_5 is not None
        and fast_5 > slow_5
        and close_5m[-1] > slow_5
    )
    readings.append(
        IndicatorReading(
            name="Tendencia 5m",
            passed=trend_5_ok,
            detail=_ema_detail(close_5m[-1], fast_5, slow_5),
        )
    )
    if not trend_5_ok:
        reasons.append(_reason("trend_5m"))

    fast_1 = last_ema(close_1m, EMA_FAST)
    slow_1 = last_ema(close_1m, EMA_SLOW)
    trend_1_ok = fast_1 is not None and slow_1 is not None and fast_1 > slow_1
    readings.append(
        IndicatorReading(
            name="Tendencia 1m",
            passed=trend_1_ok,
            detail=_ema_detail(close_1m[-1], fast_1, slow_1),
        )
    )
    if not trend_1_ok:
        reasons.append(_reason("trend_1m"))

    vwap = rolling_vwap(candles_1m, VWAP_WINDOW)
    vwap_ok = vwap is not None and close_1m[-1] >= vwap
    readings.append(
        IndicatorReading(
            name="VWAP",
            passed=vwap_ok,
            detail="Sin VWAP." if vwap is None else f"Cierre {close_1m[-1]:.6g} y VWAP {vwap:.6g}.",
        )
    )
    if not vwap_ok:
        reasons.append(_reason("vwap"))

    rsi_value = rsi(close_1m, RSI_PERIOD)
    rsi_ok = rsi_value is not None and RSI_MIN <= rsi_value <= RSI_MAX
    readings.append(
        IndicatorReading(
            name="RSI",
            passed=rsi_ok,
            detail="Sin RSI." if rsi_value is None else f"RSI {rsi_value:.1f}. Banda {RSI_MIN:.0f}-{RSI_MAX:.0f}.",
        )
    )
    if not rsi_ok:
        reasons.append(_reason("rsi"))

    atr_value = atr(candles_1m, ATR_PERIOD)
    atr_pct = None if atr_value is None or close_1m[-1] <= 0 else atr_value / close_1m[-1] * 100
    atr_ok = atr_pct is not None and ATR_PCT_MIN <= atr_pct <= ATR_PCT_MAX
    readings.append(
        IndicatorReading(
            name="ATR",
            passed=atr_ok,
            detail="Sin ATR." if atr_pct is None else f"ATR {atr_pct:.3f}% del precio.",
        )
    )
    if not atr_ok:
        reasons.append(_reason("atr"))

    ratio = volume_ratio(candles_1m, VOLUME_AVG)
    volume_ok = ratio is not None and ratio >= MIN_VOLUME_RATIO
    readings.append(
        IndicatorReading(
            name="Volumen",
            passed=volume_ok,
            detail="Sin volumen." if ratio is None else f"Última vela a {ratio:.2f} de su media.",
        )
    )
    if not volume_ok:
        reasons.append(_reason("volume"))

    for plugin in settings.custom_indicators:
        reading = evaluate_plugin(plugin, candles_1m, candles_5m)
        readings.append(reading)
        if not reading.passed:
            reasons.append(Reason(code=f"plugin_{plugin.kind}", message=reading.detail))

    if plan is None or reasons:
        return _decision(symbol, reasons, readings)

    score = _score(plan, view.imbalance, regime.name)
    if score.total + 1e-9 < MIN_SCORE:
        reasons.append(
            Reason(
                code="low_score",
                message=f"La confluencia quedó en {score.total:.0f}, debajo de {MIN_SCORE:.0f}.",
            )
        )
        return _decision(symbol, reasons, readings)

    signal = Signal(
        symbol=symbol,
        entry=plan.entry,
        stop=plan.stop,
        take_profit=plan.take_profit,
        risk_pct=plan.risk_pct,
        profit_pct=plan.profit_pct,
        reward_risk=plan.reward_risk,
        target_pct=settings.target_pct,
        exit_mode=settings.exit_mode,
        score=score.total,
        score_breakdown=score,
        support_low=plan.support.price_low,
        support_high=plan.support.price_high,
        support_notional=plan.support.notional,
        resistance_low=None if plan.resistance is None else plan.resistance.price_low,
        readings=readings,
        reasons=[
            Reason(
                code="qualified",
                message=(
                    f"Soporte {plan.support.price_low:.6g}-{plan.support.price_high:.6g} "
                    f"con fuerza {plan.support.strength:.1f}x. "
                    f"Salida {plan.profit_pct:.2f}% y R:R {plan.reward_risk:.2f}."
                ),
            )
        ],
    )
    return SymbolDecision(symbol=symbol, accepted=True, reasons=signal.reasons, readings=readings, signal=signal)


def _score(plan, imbalance: float, regime_name: str) -> ScoreBreakdown:
    extra = plan.support.strength / WALL_MULTIPLIER
    strength = min(10.0, max(0.0, (extra - 1) * 5))
    distance = _distance(plan.entry, plan.support.price_high)
    proximity = max(0.0, 8.0 * (1 - distance / PROXIMITY_BPS))
    imbalance_points = min(7.0, max(0.0, (imbalance - MIN_IMBALANCE) * 7))
    regime_points = 5.0 if regime_name == "bullish" else 0.0
    room = 0.0
    if plan.resistance is not None and plan.resistance.price_low > plan.take_profit:
        room = 5.0
    elif plan.resistance is None:
        room = 2.0
    total = min(
        SCORE_CAP,
        70 + strength + proximity + imbalance_points + regime_points + room,
    )
    return ScoreBreakdown(
        base=70,
        strength=strength,
        proximity=proximity,
        imbalance=imbalance_points,
        regime=regime_points,
        room=room,
        total=total,
    )


def _distance(entry: float, block_high: float) -> float:
    if block_high >= entry:
        return 0.0
    return (entry - block_high) / entry * 10_000


def _reason(code: str) -> Reason:
    return Reason(code=code, message=_MESSAGES[code])


def _decision(symbol: str, reasons: list[Reason], readings: list[IndicatorReading]) -> SymbolDecision:
    unique: list[Reason] = []
    seen: set[str] = set()
    for reason in reasons:
        if reason.code in seen:
            continue
        seen.add(reason.code)
        unique.append(reason)
    return SymbolDecision(symbol=symbol, accepted=False, reasons=unique, readings=readings)


def _ema_detail(close: float, fast: float | None, slow: float | None) -> str:
    if fast is None or slow is None:
        return "Sin medias."
    return f"Cierre {close:.6g}, EMA9 {fast:.6g}, EMA21 {slow:.6g}."
