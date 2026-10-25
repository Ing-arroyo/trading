from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ancla.cornerstone import (
    DEFAULT_MAX_CUSTOM,
    MAX_CUSTOM_INDICATORS_CAP,
    REWARD_RISK_DEFAULT,
    REWARD_RISK_MAX,
    REWARD_RISK_MIN,
    TARGET_PCT_DEFAULT,
    TARGET_PCT_MAX,
    TARGET_PCT_MIN,
)

PluginKind = Literal["rsi_band", "ema_trend", "vwap_side", "volume_ratio", "atr_pct_band"]
ExitMode = Literal["target", "best_rr"]
RegimeName = Literal["bullish", "neutral", "risk_off", "unknown"]


class PluginSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PluginKind
    params: dict[str, float] = Field(default_factory=dict)


class ScanSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_pct: float = TARGET_PCT_DEFAULT
    reward_risk: float = REWARD_RISK_DEFAULT
    exit_mode: ExitMode = "target"
    max_custom_indicators: int = DEFAULT_MAX_CUSTOM
    custom_indicators: list[PluginSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_bounds(self) -> "ScanSettings":
        if not TARGET_PCT_MIN <= self.target_pct <= TARGET_PCT_MAX:
            raise ValueError(
                f"La ganancia debe estar entre {TARGET_PCT_MIN}% y {TARGET_PCT_MAX}%."
            )
        if not REWARD_RISK_MIN <= self.reward_risk <= REWARD_RISK_MAX:
            raise ValueError(
                f"La relación beneficio/riesgo debe estar entre {REWARD_RISK_MIN} y {REWARD_RISK_MAX}."
            )
        if not 0 <= self.max_custom_indicators <= MAX_CUSTOM_INDICATORS_CAP:
            raise ValueError(
                f"El límite de indicadores propios no puede pasar de {MAX_CUSTOM_INDICATORS_CAP}."
            )
        from ancla.plugins import normalize_plugins

        self.custom_indicators = normalize_plugins(
            self.custom_indicators,
            self.max_custom_indicators,
        )
        return self


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class Level(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    quantity: float

    @property
    def notional(self) -> float:
        return self.price * self.quantity


class Ticker(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    quote_volume: float
    last_price: float


class OrderBook(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]


class UniverseItem(BaseModel):
    symbol: str
    quote_volume: float
    last_price: float
    anchor: bool = False


class LiquidityBlock(BaseModel):
    side: Literal["bid", "ask"]
    price_low: float
    price_high: float
    notional: float
    strength: float
    distance_bps: float


class BookView(BaseModel):
    best_bid: float
    best_ask: float
    mid: float
    spread_bps: float
    imbalance: float
    highest_ask: float
    lowest_bid: float
    supports: list[LiquidityBlock]
    resistances: list[LiquidityBlock]


class IndicatorReading(BaseModel):
    name: str
    passed: bool
    detail: str


class Reason(BaseModel):
    code: str
    message: str


class ScoreBreakdown(BaseModel):
    base: float
    strength: float
    proximity: float
    imbalance: float
    regime: float
    room: float
    total: float


class RiskPlan(BaseModel):
    entry: float
    stop: float
    take_profit: float
    risk_pct: float
    profit_pct: float
    reward_risk: float
    support: LiquidityBlock
    resistance: LiquidityBlock | None = None


class Signal(BaseModel):
    symbol: str
    side: Literal["LONG"] = "LONG"
    entry: float
    stop: float
    take_profit: float
    risk_pct: float
    profit_pct: float
    reward_risk: float
    target_pct: float
    exit_mode: ExitMode
    score: float
    score_breakdown: ScoreBreakdown
    support_low: float
    support_high: float
    support_notional: float
    resistance_low: float | None = None
    readings: list[IndicatorReading]
    reasons: list[Reason]


class SymbolDecision(BaseModel):
    symbol: str
    accepted: bool
    reasons: list[Reason]
    readings: list[IndicatorReading]
    signal: Signal | None = None


class BtcRegime(BaseModel):
    name: RegimeName
    detail: str
    return_pct: float | None = None
    close: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None


class ScanReport(BaseModel):
    source: str
    execution_mode: str
    generated_at: str
    elapsed_ms: int
    settings: ScanSettings
    btc: BtcRegime
    universe: list[UniverseItem]
    signals: list[Signal]
    rejections: list[SymbolDecision]
