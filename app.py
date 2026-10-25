"""Entrada de Streamlit. En el despliegue, el archivo principal es app.py."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from ancla.adapters.binance import BinancePublicMarket
from ancla.adapters.demo import DemoMarket
from ancla.models import ScanReport, ScanSettings
from ancla.ports import ScanError
from ancla.scanner import scan

st.set_page_config(page_title="Ancla", layout="wide")
st.title("Ancla")
st.caption("Buscador de entradas de scalping. Solo análisis: no envía órdenes.")

with st.sidebar:
    source = st.selectbox("Mercado", ["binance", "demo"], format_func=lambda item: "Binance" if item == "binance" else "Demo")
    target_pct = st.number_input("Ganancia mínima %", min_value=0.3, max_value=2.0, value=1.0, step=0.1)
    reward_risk = st.number_input("Beneficio / riesgo mínimo", min_value=1.5, max_value=4.0, value=2.0, step=0.1)
    exit_mode = st.selectbox(
        "Salida",
        ["target", "best_rr"],
        format_func=lambda item: "Asegurar la ganancia pedida" if item == "target" else "Extender hasta la resistencia",
    )
    search = st.button("Buscar ahora", type="primary")
    radar = st.toggle("Radar cada 90 segundos")

settings = ScanSettings(target_pct=float(target_pct), reward_risk=float(reward_risk), exit_mode=exit_mode)


def render(report: ScanReport) -> None:
    st.subheader(report.btc.detail)
    st.write(
        f"Universo: {', '.join(item.symbol.removesuffix('USDT') for item in report.universe)}"
        f" · {report.elapsed_ms} ms · {report.source}"
    )
    if not report.signals:
        st.info("Ningún par cumplió la confluencia en esta pasada.")
    for signal in report.signals:
        st.markdown(
            f"**{signal.symbol.removesuffix('USDT')}** · puntaje {signal.score:.0f}  \n"
            f"Entrada `{signal.entry:.8g}` · stop `{signal.stop:.8g}` · "
            f"salida `{signal.take_profit:.8g}` · +{signal.profit_pct:.2f}% · "
            f"R:R {signal.reward_risk:.2f}"
        )
    with st.expander(f"Sin entrada ({len(report.rejections)})"):
        for decision in report.rejections:
            reason = " ".join(item.message for item in decision.reasons)
            st.write(f"**{decision.symbol.removesuffix('USDT')}** — {reason}")


async def run_scan() -> ScanReport:
    if source == "demo":
        return await scan(DemoMarket(), settings)
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await scan(BinancePublicMarket(client), settings)


def search_once() -> None:
    with st.spinner("Leyendo el libro…"):
        try:
            report = asyncio.run(run_scan())
        except ScanError as exc:
            st.error(str(exc))
            return
    render(report)


if radar:
    @st.fragment(run_every=90)
    def radar_pass() -> None:
        search_once()

    radar_pass()
elif search:
    search_once()
else:
    st.write("Elige Binance y pulsa **Buscar ahora**, o activa el radar para repetir la búsqueda.")
