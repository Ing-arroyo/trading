import { useEffect, useState } from "react";
import { getJson, sendJson, type RadarView, type Settings } from "./api";

const EMPTY: RadarView = {
  running: false,
  phase: "idle",
  source: null,
  interval_seconds: null,
  window_minutes: null,
  started_at: null,
  ends_at: null,
  next_scan_at: null,
  last_scan_at: null,
  last_error: null,
  scans: 0,
  quiet: 0,
  btc_name: null,
  btc_detail: null,
  universe: [],
  active: [],
  hits: [],
};

export function RadarPanel({ settings }: { settings: Settings }) {
  const [source, setSource] = useState<"demo" | "binance">("binance");
  const [intervalSeconds, setIntervalSeconds] = useState(90);
  const [windowMinutes, setWindowMinutes] = useState(60);
  const [view, setView] = useState<RadarView>(EMPTY);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let gone = false;
    async function pull() {
      try {
        const next = await getJson<RadarView>("/api/radar");
        if (!gone) setView(next);
      } catch (reason) {
        if (!gone) setError(reason instanceof Error ? reason.message : "No se pudo leer el radar.");
      }
    }
    void pull();
    const poll = window.setInterval(() => void pull(), 2000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      gone = true;
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, []);

  const minimum = source === "binance" ? 60 : 15;
  const fresh = new Set(
    view.hits.filter((hit) => hit.detected_at === view.last_scan_at).map((hit) => hit.symbol),
  );

  async function start() {
    setPending(true);
    setError("");
    try {
      const next = await sendJson<RadarView>("/api/radar/start", "POST", {
        source,
        interval_seconds: intervalSeconds,
        window_minutes: windowMinutes,
        settings,
      });
      setView(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo activar el radar.");
    } finally {
      setPending(false);
    }
  }

  async function stop() {
    setPending(true);
    setError("");
    try {
      setView(await sendJson<RadarView>("/api/radar/stop", "POST", {}));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo detener el radar.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="radar">
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void start();
        }}
      >
        <h2>Radar</h2>
        <p className="lede">
          Recorre el universo completo cada cierto tiempo, dentro de una ventana.
          Las apariciones quedan aquí y no reemplazan el análisis manual.
        </p>
        <p className="meta">
          Estrategia al activar: {settings.target_pct}% · R:R {settings.reward_risk} ·{" "}
          {settings.exit_mode === "target" ? "salida fija" : "salida extendida"}
        </p>
        <label>
          Mercado
          <select
            value={source}
            disabled={view.running}
            onChange={(event) => {
              const next = event.target.value as "demo" | "binance";
              setSource(next);
              setIntervalSeconds((current) => Math.max(current, next === "binance" ? 60 : 15));
            }}
          >
            <option value="demo">Demo</option>
            <option value="binance">Binance</option>
          </select>
        </label>
        <label>
          Cada cuántos segundos
          <input
            type="number"
            min={minimum}
            max={900}
            step={15}
            value={intervalSeconds}
            disabled={view.running}
            onChange={(event) => setIntervalSeconds(Number(event.target.value))}
          />
        </label>
        <label>
          Durante cuántos minutos
          <input
            type="number"
            min={5}
            max={240}
            step={5}
            value={windowMinutes}
            disabled={view.running}
            onChange={(event) => setWindowMinutes(Number(event.target.value))}
          />
        </label>
        <p className="meta">Binance no baja de 60 segundos. El demo puede bajar a 15.</p>
        {view.running ? (
          <button type="button" onClick={() => void stop()} disabled={pending}>
            Detener radar
          </button>
        ) : (
          <button type="submit" disabled={pending}>
            {pending ? "Activando…" : "Activar radar"}
          </button>
        )}
        {error && <p className="banner">{error}</p>}
      </form>

      <div className="radar-feed">
        <article className={`panel regime ${view.btc_name ?? "unknown"}`}>
          <p className="eyebrow">{phaseLabel(view)}</p>
          <h2>{view.btc_detail ?? "El radar todavía no hizo una pasada."}</h2>
          <p className="meta">
            {view.scans} {view.scans === 1 ? "pasada" : "pasadas"}
            {view.running && view.next_scan_at && ` · próxima en ${left(view.next_scan_at, now)}`}
            {view.ends_at && view.running && ` · cierra en ${left(view.ends_at, now)}`}
            {view.scans > 0 && ` · ${view.quiet} sin entrada`}
          </p>
          {view.last_error && <p className="banner">{view.last_error}</p>}
          {view.universe.length > 0 && (
            <div className="universe">
              {view.universe.map((symbol) => (
                <span
                  key={symbol}
                  className={symbol === "BTCUSDT" ? "anchor" : fresh.has(symbol) ? "ready" : ""}
                >
                  {symbol.replace("USDT", "")}
                </span>
              ))}
            </div>
          )}
        </article>

        <article className="panel">
          <h2>En esta pasada</h2>
          {view.active.length === 0 ? (
            <p className="lede">Sin entrada en la última búsqueda.</p>
          ) : (
            <ul className="hits">
              {view.active.map((hit) => (
                <Hit key={hit.symbol} hit={hit} fresh={fresh.has(hit.symbol)} />
              ))}
            </ul>
          )}
        </article>

        <article className="panel">
          <h2>Apariciones de la ventana</h2>
          {view.hits.length === 0 ? (
            <p className="lede">Cuando un par cumpla la estrategia, queda anotado aquí una vez.</p>
          ) : (
            <ul className="hits">
              {view.hits.map((hit, index) => (
                <Hit key={`${hit.detected_at}-${hit.symbol}-${index}`} hit={hit} stamped />
              ))}
            </ul>
          )}
        </article>
      </div>
    </section>
  );
}

function Hit({
  hit,
  fresh = false,
  stamped = false,
}: {
  hit: RadarView["hits"][number];
  fresh?: boolean;
  stamped?: boolean;
}) {
  return (
    <li>
      <strong>
        {hit.symbol.replace("USDT", "")}
        {fresh && <em> nueva</em>}
      </strong>
      <span>
        {stamped && `${clock(hit.detected_at)} · `}
        entrada {formatPrice(hit.entry)} · stop {formatPrice(hit.stop)} · salida{" "}
        {formatPrice(hit.take_profit)} · +{hit.profit_pct.toFixed(2)}% · R:R {hit.reward_risk.toFixed(2)}
      </span>
    </li>
  );
}

function phaseLabel(view: RadarView): string {
  if (view.phase === "scanning") return "Leyendo el libro";
  if (view.phase === "waiting") return "Radar activo";
  if (view.phase === "finished") return "Ventana cerrada";
  return "Radar en espera";
}

function left(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes <= 0) return `${rest}s`;
  return `${minutes} min ${rest.toString().padStart(2, "0")}s`;
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (price >= 1) return price.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return price.toLocaleString("en-US", { maximumFractionDigits: 6 });
}
