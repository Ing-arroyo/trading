import { useEffect, useMemo, useState } from "react";
import {
  getJson,
  sendJson,
  type PluginCatalogItem,
  type PluginSpec,
  type ScanReport,
  type Settings,
  type Signal,
} from "./api";
import { RadarPanel } from "./Radar";

const EMPTY_SETTINGS: Settings = {
  target_pct: 1,
  reward_risk: 2,
  exit_mode: "target",
  max_custom_indicators: 3,
  custom_indicators: [],
};

export function App() {
  const [catalog, setCatalog] = useState<PluginCatalogItem[]>([]);
  const [cap, setCap] = useState(5);
  const [settings, setSettings] = useState<Settings>(EMPTY_SETTINGS);
  const [draftKind, setDraftKind] = useState("");
  const [draftParams, setDraftParams] = useState<Record<string, number>>({});
  const [report, setReport] = useState<ScanReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [booting, setBooting] = useState(true);
  const [tab, setTab] = useState<"analysis" | "radar">("analysis");

  useEffect(() => {
    Promise.all([
      getJson<{ cap: number; plugins: PluginCatalogItem[] }>("/api/plugins/catalog"),
      getJson<Settings>("/api/settings"),
    ])
      .then(([plugins, stored]) => {
        setCatalog(plugins.plugins);
        setCap(plugins.cap);
        setSettings(stored);
        if (plugins.plugins[0]) selectKind(plugins.plugins[0], setDraftKind, setDraftParams);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setBooting(false));
  }, []);

  const draft = catalog.find((item) => item.kind === draftKind) ?? catalog[0];
  const used = new Set(settings.custom_indicators.map((item) => item.kind));
  const limit = Math.min(settings.max_custom_indicators, cap);

  async function analyze(source: "demo" | "binance") {
    setBusy(true);
    setError("");
    try {
      const next = await sendJson<ScanReport>("/api/scan", "POST", { source, settings });
      setReport(next);
      setSettings(next.settings);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo analizar.");
    } finally {
      setBusy(false);
    }
  }

  function addPlugin() {
    if (!draft || used.has(draft.kind) || settings.custom_indicators.length >= limit) return;
    const plugin: PluginSpec = { kind: draft.kind, params: { ...draftParams } };
    setSettings({ ...settings, custom_indicators: [...settings.custom_indicators, plugin] });
  }

  const signalSymbols = useMemo(
    () => new Set(report?.signals.map((signal) => signal.symbol) ?? []),
    [report],
  );

  return (
    <main>
      <header className="top">
        <div>
          <p className="eyebrow">Scalping · libro de órdenes</p>
          <h1>Ancla</h1>
        </div>
        <p className="lock">Solo análisis. Esta versión no envía órdenes.</p>
      </header>

      {error && tab === "analysis" && <p className="banner">{error}</p>}

      <nav className="tabs">
        <button type="button" className={tab === "analysis" ? "active" : ""} onClick={() => setTab("analysis")}>
          Análisis
        </button>
        <button type="button" className={tab === "radar" ? "active" : ""} onClick={() => setTab("radar")}>
          Radar
        </button>
      </nav>

      {tab === "radar" ? (
        <RadarPanel settings={settings} />
      ) : (
      <section className="layout">
        <form
          className="panel settings"
          onSubmit={(event) => {
            event.preventDefault();
            void analyze("binance");
          }}
        >
          <h2>Estrategia principal</h2>
          <p className="lede">
            El libro marca soporte, stop y si el objetivo cabe. Bitcoin se muestra aparte
            y no veta. Los indicadores propios solo pueden vetar.
          </p>
          <label>
            Ganancia mínima (%)
            <input
              type="number"
              min={0.3}
              max={2}
              step={0.1}
              value={settings.target_pct}
              onChange={(event) =>
                setSettings({ ...settings, target_pct: Number(event.target.value) })
              }
            />
          </label>
          <label>
            Beneficio / riesgo mínimo
            <input
              type="number"
              min={1.5}
              max={4}
              step={0.1}
              value={settings.reward_risk}
              onChange={(event) =>
                setSettings({ ...settings, reward_risk: Number(event.target.value) })
              }
            />
          </label>
          <label>
            Salida
            <select
              value={settings.exit_mode}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  exit_mode: event.target.value as Settings["exit_mode"],
                })
              }
            >
              <option value="target">Asegurar la ganancia pedida</option>
              <option value="best_rr">Extender hasta la resistencia, máximo el doble</option>
            </select>
          </label>
          <label>
            Límite de indicadores propios
            <input
              type="number"
              min={0}
              max={cap}
              step={1}
              value={settings.max_custom_indicators}
              onChange={(event) => {
                const nextLimit = Number(event.target.value);
                setSettings({
                  ...settings,
                  max_custom_indicators: nextLimit,
                  custom_indicators: settings.custom_indicators.slice(0, nextLimit),
                });
              }}
            />
          </label>

          <div className="plugins">
            <h3>Indicadores propios</h3>
            <p>{settings.custom_indicators.length} de {limit}</p>
            {settings.custom_indicators.map((plugin) => {
              const item = catalog.find((candidate) => candidate.kind === plugin.kind);
              return (
                <div className="chip" key={plugin.kind}>
                  <strong>{item?.label ?? plugin.kind}</strong>
                  <span>{formatParams(plugin)}</span>
                  <button
                    type="button"
                    onClick={() =>
                      setSettings({
                        ...settings,
                        custom_indicators: settings.custom_indicators.filter(
                          (candidate) => candidate.kind !== plugin.kind,
                        ),
                      })
                    }
                  >
                    Quitar
                  </button>
                </div>
              );
            })}
            {draft && (
              <div className="draft">
                <select
                  value={draft.kind}
                  onChange={(event) => {
                    const next = catalog.find((item) => item.kind === event.target.value);
                    if (next) selectKind(next, setDraftKind, setDraftParams);
                  }}
                >
                  {catalog.map((item) => (
                    <option key={item.kind} value={item.kind} disabled={used.has(item.kind)}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <p>{draft.description}</p>
                {draft.fields.map((field) => (
                  <label key={field.key}>
                    {field.label}
                    <input
                      type="number"
                      min={field.min}
                      max={field.max}
                      step="any"
                      value={draftParams[field.key] ?? field.default}
                      onChange={(event) =>
                        setDraftParams({ ...draftParams, [field.key]: Number(event.target.value) })
                      }
                    />
                  </label>
                ))}
                <button
                  type="button"
                  disabled={used.has(draft.kind) || settings.custom_indicators.length >= limit}
                  onClick={addPlugin}
                >
                  Añadir filtro
                </button>
              </div>
            )}
          </div>

          <div className="actions">
            <button type="submit" disabled={busy || booting}>
              {busy ? "Leyendo el libro…" : "Analizar Binance"}
            </button>
            <button type="button" className="secondary" disabled={busy || booting} onClick={() => analyze("demo")}>
              Probar con mercado demo
            </button>
          </div>
        </form>

        <section className="results">
          {!report && (
            <article className="panel empty">
              <h2>Todavía no hay un análisis</h2>
              <p>
                El demo recorre diez pares con libros construidos para mostrar una entrada válida,
                un soporte demasiado lejos y una resistencia que tapa el objetivo.
              </p>
            </article>
          )}
          {report && (
            <>
              <article className={`panel regime ${report.btc.name}`}>
                <p className="eyebrow">Bitcoin · {labelRegime(report.btc.name)}</p>
                <h2>{report.btc.detail}</h2>
                <p className="meta">
                  {report.source === "demo" ? "Mercado demo" : "Binance spot, datos públicos"}
                  {" · "}
                  {report.elapsed_ms} ms
                  {report.btc.return_pct !== null && ` · retorno reciente ${report.btc.return_pct.toFixed(2)}%`}
                </p>
                <div className="universe">
                  {report.universe.map((item) => (
                    <span
                      key={item.symbol}
                      className={
                        item.anchor ? "anchor" : signalSymbols.has(item.symbol) ? "ready" : ""
                      }
                    >
                      {item.symbol.replace("USDT", "")}
                    </span>
                  ))}
                </div>
              </article>

              <div className="signals">
                {report.signals.length === 0 && (
                  <article className="panel empty">
                    <h2>Ningún par cumplió la confluencia</h2>
                    <p>Los rechazos de abajo dicen qué compuerta falló.</p>
                  </article>
                )}
                {report.signals.map((signal) => (
                  <SignalCard key={signal.symbol} signal={signal} />
                ))}
              </div>

              <article className="panel">
                <h2>Sin entrada</h2>
                <ul className="rejections">
                  {report.rejections.map((decision) => (
                    <li key={decision.symbol}>
                      <strong>{decision.symbol.replace("USDT", "")}</strong>
                      <span>{decision.reasons.map((reason) => reason.message).join(" ")}</span>
                    </li>
                  ))}
                </ul>
              </article>
            </>
          )}
        </section>
      </section>
      )}
    </main>
  );
}

function SignalCard({ signal }: { signal: Signal }) {
  return (
    <article className="panel signal">
      <div className="signal-head">
        <div>
          <p className="eyebrow">Largo</p>
          <h2>{signal.symbol.replace("USDT", "")}</h2>
        </div>
        <p className="score">{Math.round(signal.score)}</p>
      </div>
      <dl>
        <div>
          <dt>Entrada</dt>
          <dd>{formatPrice(signal.entry)}</dd>
        </div>
        <div>
          <dt>Stop</dt>
          <dd>{formatPrice(signal.stop)}</dd>
        </div>
        <div>
          <dt>Salida</dt>
          <dd>{formatPrice(signal.take_profit)}</dd>
        </div>
      </dl>
      <p className="figures">
        <span>+{signal.profit_pct.toFixed(2)}%</span>
        <span>riesgo {signal.risk_pct.toFixed(2)}%</span>
        <span>R:R {signal.reward_risk.toFixed(2)}</span>
      </p>
      <PlanTrack signal={signal} />
      <p className="reason">{signal.reasons[0]?.message}</p>
      <ul className="readings">
        {signal.readings.map((reading) => (
          <li key={reading.name} className={reading.passed ? "pass" : "fail"}>
            {reading.name}
          </li>
        ))}
      </ul>
    </article>
  );
}

function PlanTrack({ signal }: { signal: Signal }) {
  const points = [
    { label: "Stop", pct: percentFrom(signal.entry, signal.stop), place: "above" },
    { label: "Entrada", pct: 0, place: "below" },
    { label: "Salida", pct: percentFrom(signal.entry, signal.take_profit), place: "above" },
  ];
  if (signal.resistance_low) {
    points.push({
      label: "Resistencia",
      pct: percentFrom(signal.entry, signal.resistance_low),
      place: "below",
    });
  }
  const min = -0.8;
  const max = 2.4;
  return (
    <div className="track" aria-hidden="true">
      {points.map((point) => (
        <span
          key={point.label}
          className={point.place}
          style={{ left: `${clamp(((point.pct - min) / (max - min)) * 100)}%` }}
        >
          {point.label}
        </span>
      ))}
    </div>
  );
}

function percentFrom(entry: number, price: number): number {
  return ((price - entry) / entry) * 100;
}

function clamp(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function selectKind(
  item: PluginCatalogItem,
  setKind: (kind: string) => void,
  setParams: (params: Record<string, number>) => void,
) {
  setKind(item.kind);
  setParams(Object.fromEntries(item.fields.map((field) => [field.key, field.default])));
}

function formatParams(plugin: PluginSpec): string {
  return Object.entries(plugin.params)
    .map(([key, value]) => `${key} ${value}`)
    .join(" · ");
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (price >= 1) return price.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return price.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function labelRegime(name: ScanReport["btc"]["name"]): string {
  if (name === "bullish") return "a favor";
  if (name === "neutral") return "neutral";
  if (name === "risk_off") return "en contra";
  return "sin régimen";
}
