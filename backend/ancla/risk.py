"""Salida de la estrategia principal.

La ganancia pedida es un suelo. La relación beneficio/riesgo es el otro suelo.
El stop vive debajo del bloque de soporte, no en un porcentaje suelto.
Si el bloque obliga a arriesgar más de lo que esa relación permite, no hay entrada.
"""

from __future__ import annotations

from ancla.cornerstone import BUFFER_BPS, PROXIMITY_BPS, TARGET_EXTENSION_CAP
from ancla.models import LiquidityBlock, RiskPlan, ScanSettings


def plan_exit(
    entry: float,
    support: LiquidityBlock,
    resistances: list[LiquidityBlock],
    highest_ask: float,
    settings: ScanSettings,
) -> tuple[RiskPlan | None, str | None]:
    if entry <= 0 or support.price_low <= 0:
        return None, "risk_exceeds_plan"
    stop = support.price_low * (1 - BUFFER_BPS / 10_000)
    if stop >= entry:
        return None, "risk_exceeds_plan"
    risk_pct = (entry - stop) / entry * 100
    max_risk = settings.target_pct / settings.reward_risk
    if risk_pct > max_risk + 1e-9:
        return None, "risk_exceeds_plan"

    floor_tp = entry * (1 + settings.target_pct / 100)
    cap_tp = entry * (1 + settings.target_pct * TARGET_EXTENSION_CAP / 100)
    if highest_ask < floor_tp:
        return None, "book_does_not_cover_target"

    resistance = _next_resistance(resistances, entry)
    room = None
    if resistance is not None:
        room = resistance.price_low * (1 - BUFFER_BPS / 10_000)
        if room < floor_tp:
            return None, "resistance_blocks_target"

    if settings.exit_mode == "best_rr" and room is not None:
        take_profit = min(room, cap_tp)
    else:
        take_profit = floor_tp

    if take_profit <= entry:
        return None, "reward_too_small"
    profit_pct = (take_profit - entry) / entry * 100
    reward_risk = profit_pct / risk_pct
    if profit_pct + 1e-9 < settings.target_pct or reward_risk + 1e-9 < settings.reward_risk:
        return None, "reward_too_small"
    return (
        RiskPlan(
            entry=entry,
            stop=stop,
            take_profit=take_profit,
            risk_pct=risk_pct,
            profit_pct=profit_pct,
            reward_risk=reward_risk,
            support=support,
            resistance=resistance,
        ),
        None,
    )


def supports_in_range(supports: list[LiquidityBlock], entry: float) -> list[LiquidityBlock]:
    found: list[LiquidityBlock] = []
    for block in supports:
        if block.price_low > entry:
            continue
        if block.price_high >= entry:
            distance = 0.0
        else:
            distance = (entry - block.price_high) / entry * 10_000
        if distance <= PROXIMITY_BPS:
            found.append(block)
    return found


def _next_resistance(
    resistances: list[LiquidityBlock],
    entry: float,
) -> LiquidityBlock | None:
    above = [block for block in resistances if block.price_low > entry]
    if not above:
        return None
    return min(above, key=lambda block: block.price_low)
