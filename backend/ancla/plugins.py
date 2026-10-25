"""Indicadores que el usuario puede sumar.

Son filtros adicionales. Si fallan, anulan la entrada. No suman permiso
cuando el libro o Bitcoin ya dijeron que no.
"""

from __future__ import annotations

from ancla.cornerstone import MAX_CUSTOM_INDICATORS_CAP
from ancla.indicators import atr, closes, last_ema, rolling_vwap, rsi, volume_ratio
from ancla.models import Candle, IndicatorReading, PluginSpec

CATALOG: list[dict] = [
    {
        "kind": "rsi_band",
        "label": "RSI en banda",
        "description": "Exige que el RSI de 1m esté dentro de un rango más estrecho.",
        "fields": [
            {"key": "min", "label": "Mínimo", "default": 45, "min": 1, "max": 90},
            {"key": "max", "label": "Máximo", "default": 60, "min": 5, "max": 95},
        ],
    },
    {
        "kind": "ema_trend",
        "label": "Cruce de medias",
        "description": "Exige una EMA rápida por encima de una EMA lenta.",
        "fields": [
            {"key": "fast", "label": "Rápida", "default": 20, "min": 2, "max": 50},
            {"key": "slow", "label": "Lenta", "default": 50, "min": 5, "max": 120},
            {"key": "timeframe", "label": "Minutos (1 o 5)", "default": 5, "min": 1, "max": 5},
        ],
    },
    {
        "kind": "vwap_side",
        "label": "Precio sobre VWAP",
        "description": "Exige el cierre de 1m por encima de un VWAP móvil.",
        "fields": [
            {"key": "window", "label": "Velas", "default": 30, "min": 10, "max": 120},
        ],
    },
    {
        "kind": "volume_ratio",
        "label": "Volumen relativo",
        "description": "Exige que la última vela negocie por encima de su media.",
        "fields": [
            {"key": "minimum", "label": "Mínimo frente a la media", "default": 1.1, "min": 0.5, "max": 3},
        ],
    },
    {
        "kind": "atr_pct_band",
        "label": "Volatilidad ATR",
        "description": "Exige que el ATR, en porcentaje, quede dentro de una banda.",
        "fields": [
            {"key": "min", "label": "Mínimo %", "default": 0.08, "min": 0.01, "max": 1},
            {"key": "max", "label": "Máximo %", "default": 0.6, "min": 0.05, "max": 2},
        ],
    },
]

_FIELDS = {item["kind"]: item["fields"] for item in CATALOG}


def normalize_plugins(plugins: list[PluginSpec], limit: int) -> list[PluginSpec]:
    if len(plugins) > limit:
        raise ValueError(
            f"Hay {len(plugins)} indicadores propios y el límite de esta configuración es {limit}."
        )
    if len(plugins) > MAX_CUSTOM_INDICATORS_CAP:
        raise ValueError(
            f"El máximo absoluto de indicadores propios es {MAX_CUSTOM_INDICATORS_CAP}."
        )
    kinds = [plugin.kind for plugin in plugins]
    if len(kinds) != len(set(kinds)):
        raise ValueError("Cada indicador propio tiene que ser de un tipo distinto.")
    return [_normalize(plugin) for plugin in plugins]


def evaluate_plugin(
    plugin: PluginSpec,
    candles_1m: list[Candle],
    candles_5m: list[Candle],
) -> IndicatorReading:
    params = plugin.params
    if plugin.kind == "rsi_band":
        value = rsi(closes(candles_1m), 14)
        if value is None:
            return _fail(plugin.kind, "RSI propio sin datos.")
        passed = params["min"] <= value <= params["max"]
        return IndicatorReading(
            name="RSI propio",
            passed=passed,
            detail=f"RSI {value:.1f} frente a banda {params['min']:.0f}-{params['max']:.0f}.",
        )
    if plugin.kind == "ema_trend":
        series = closes(candles_1m if params["timeframe"] == 1 else candles_5m)
        fast = last_ema(series, int(params["fast"]))
        slow = last_ema(series, int(params["slow"]))
        if fast is None or slow is None:
            return _fail("ema_trend", "Medias propias sin datos.")
        passed = fast > slow
        return IndicatorReading(
            name="Medias propias",
            passed=passed,
            detail=f"EMA {int(params['fast'])} {fast:.6g} y EMA {int(params['slow'])} {slow:.6g}.",
        )
    if plugin.kind == "vwap_side":
        value = rolling_vwap(candles_1m, int(params["window"]))
        if value is None:
            return _fail("vwap_side", "VWAP propio sin datos.")
        close = candles_1m[-1].close
        return IndicatorReading(
            name="VWAP propio",
            passed=close > value,
            detail=f"Cierre {close:.6g} y VWAP {value:.6g}.",
        )
    if plugin.kind == "volume_ratio":
        ratio = volume_ratio(candles_1m, 20)
        if ratio is None:
            return _fail("volume_ratio", "Volumen propio sin datos.")
        return IndicatorReading(
            name="Volumen propio",
            passed=ratio >= params["minimum"],
            detail=f"Ratio {ratio:.2f} frente a mínimo {params['minimum']:.2f}.",
        )
    value = atr(candles_1m, 14)
    close = candles_1m[-1].close
    if value is None or close <= 0:
        return _fail("atr_pct_band", "ATR propio sin datos.")
    atr_pct = value / close * 100
    passed = params["min"] <= atr_pct <= params["max"]
    return IndicatorReading(
        name="ATR propio",
        passed=passed,
        detail=f"ATR {atr_pct:.3f}% frente a banda {params['min']:.2f}-{params['max']:.2f}.",
    )


def _normalize(plugin: PluginSpec) -> PluginSpec:
    fields = _FIELDS[plugin.kind]
    allowed = {field["key"] for field in fields}
    unknown = set(plugin.params) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Parámetro no admitido en {plugin.kind}: {names}.")
    merged = {field["key"]: float(field["default"]) for field in fields}
    merged.update({key: float(value) for key, value in plugin.params.items()})
    for field in fields:
        value = merged[field["key"]]
        if not field["min"] <= value <= field["max"]:
            raise ValueError(f"{plugin.kind}.{field['key']} está fuera de rango.")
    if plugin.kind == "rsi_band" and merged["min"] >= merged["max"]:
        raise ValueError("En el RSI propio el mínimo tiene que ser menor que el máximo.")
    if plugin.kind == "atr_pct_band" and merged["min"] >= merged["max"]:
        raise ValueError("En el ATR propio el mínimo tiene que ser menor que el máximo.")
    if plugin.kind == "ema_trend":
        if merged["fast"] >= merged["slow"]:
            raise ValueError("La media rápida tiene que ser menor que la lenta.")
        if merged["timeframe"] not in (1, 5):
            raise ValueError("El marco de las medias propias es 1m o 5m.")
    return plugin.model_copy(update={"params": merged})


def _fail(name: str, detail: str) -> IndicatorReading:
    return IndicatorReading(name=name, passed=False, detail=detail)
