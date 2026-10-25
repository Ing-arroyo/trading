"""Punto de entrada: `python -m ancla scan --demo` y `python -m ancla serve`."""

from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from ancla.adapters.demo import DemoMarket
from ancla.ports import ScanError
from ancla.scanner import scan
from ancla.settings_store import SettingsError, load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="ancla", description="Buscador de entradas Ancla")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_command = commands.add_parser("scan", help="Corre un análisis y lo imprime")
    scan_command.add_argument("--source", choices=("demo", "binance"), default="demo")
    commands.add_parser("serve", help="Sirve la API en 127.0.0.1:8000")
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("ancla.api:app", host="127.0.0.1", port=8000)
        return
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    try:
        if args.source == "demo":
            report = asyncio.run(scan(DemoMarket(), settings))
        else:
            report = asyncio.run(_binance_scan(settings))
    except ScanError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    _print_report(report)


async def _binance_scan(settings):
    import httpx

    from ancla.adapters.binance import BinancePublicMarket

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await scan(BinancePublicMarket(client), settings)


def _print_report(report) -> None:
    print(f"Régimen Bitcoin: {report.btc.name} — {report.btc.detail}")
    print("Universo: " + ", ".join(item.symbol for item in report.universe))
    if not report.signals:
        print("Sin entradas.")
    for signal in report.signals:
        print(
            f"{signal.symbol}  entrada {signal.entry:.8g}  stop {signal.stop:.8g}  "
            f"salida {signal.take_profit:.8g}  {signal.profit_pct:.2f}%  "
            f"R:R {signal.reward_risk:.2f}  puntaje {signal.score:.0f}"
        )
    for decision in report.rejections:
        because = "; ".join(reason.message for reason in decision.reasons)
        print(f"{decision.symbol}  no opera — {because}")


if __name__ == "__main__":
    main()
