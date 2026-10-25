# Ancla

Buscador de entradas de scalping en spot. La estrategia principal lee el libro de órdenes, usa a Bitcoin como régimen y solo propone un largo cuando la ganancia pedida y la relación beneficio/riesgo caben delante del siguiente bloque de resistencia.

Esta versión no envía órdenes ni abre Telegram. Esos dos caminos existen como contrato y responden con un rechazo.

## Regla de salida

Con la configuración inicial la ganancia mínima es **1%** y la relación mínima es **2 a 1**.

- La entrada es el mejor ask.
- El stop queda debajo del bloque de soporte, con un margen de 3 puntos básicos.
- Si ese stop arriesga más que `ganancia / relación` (0,5% con los valores iniciales), no hay entrada.
- Si una resistencia visible aparece antes del objetivo, no hay entrada.
- Si el libro no llega a verse hasta el objetivo, no hay entrada.
- En modo `best_rr` la salida puede acercarse a la resistencia, sin pasar del doble de la ganancia pedida.

Los indicadores fijos son tendencia de 5m, tendencia de 1m, VWAP, RSI, ATR y volumen. Un indicador propio se suma como filtro: si falla, veta la entrada. No puede autorizarla por su cuenta. El máximo absoluto es 5 y el límite activo sale de la configuración.

El universo son 10 pares USDT. Bitcoin va siempre primero. Si Bitcoin no se puede leer, el análisis se detiene. En risk-off no hay largos.

## Streamlit

El archivo principal del despliegue es `app.py`, en la raíz del repositorio. Streamlit Cloud también usa el `requirements.txt` de esa misma raíz.

## Arranque

Desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
python -m ancla scan --demo
python -m ancla serve
```

En otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

La interfaz queda en `http://127.0.0.1:5173`. El botón de Binance usa el API público, sin clave. Entre análisis reales hay una pausa corta para no golpear el límite de consultas.

`Analizar Binance` elige en ese momento las diez criptos USDT de mayor volumen, siempre con Bitcoin delante, y descarta stablecoins y tokens apalancados.

## Radar

La pestaña Radar repite esa búsqueda global durante una ventana. El intervalo y la ventana se eligen al activarlo: Binance no baja de 60 segundos y el demo puede bajar a 15. La ventana va de 5 a 240 minutos. Un par se anota cuando aparece y no se vuelve a anotar mientras siga cumpliendo la estrategia. El análisis manual conserva su propio resultado.

## Qué queda para después

- Operar en Binance Spot sigue detrás de `AnalysisOnlyBroker`. Habilitarlo exige un interruptor explícito, clave con permiso de trading y confirmación por señal. No está cableado.
- Telegram sigue detrás de `TelegramNotifier`, apagado.
