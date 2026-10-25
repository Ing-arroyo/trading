export type ExitMode = "target" | "best_rr";
export type RegimeName = "bullish" | "neutral" | "risk_off" | "unknown";

export interface PluginField {
  key: string;
  label: string;
  default: number;
  min: number;
  max: number;
}

export interface PluginCatalogItem {
  kind: string;
  label: string;
  description: string;
  fields: PluginField[];
}

export interface PluginSpec {
  kind: string;
  params: Record<string, number>;
}

export interface Settings {
  target_pct: number;
  reward_risk: number;
  exit_mode: ExitMode;
  max_custom_indicators: number;
  custom_indicators: PluginSpec[];
}

export interface Reason {
  code: string;
  message: string;
}

export interface Reading {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Signal {
  symbol: string;
  side: "LONG";
  entry: number;
  stop: number;
  take_profit: number;
  risk_pct: number;
  profit_pct: number;
  reward_risk: number;
  score: number;
  support_low: number;
  support_high: number;
  support_notional: number;
  resistance_low: number | null;
  readings: Reading[];
  reasons: Reason[];
}

export interface UniverseItem {
  symbol: string;
  quote_volume: number;
  last_price: number;
  anchor: boolean;
}

export interface Decision {
  symbol: string;
  accepted: boolean;
  reasons: Reason[];
  readings: Reading[];
}

export interface ScanReport {
  source: string;
  execution_mode: string;
  generated_at: string;
  elapsed_ms: number;
  settings: Settings;
  btc: {
    name: RegimeName;
    detail: string;
    return_pct: number | null;
  };
  universe: UniverseItem[];
  signals: Signal[];
  rejections: Decision[];
}

export interface RadarHit {
  detected_at: string;
  symbol: string;
  entry: number;
  stop: number;
  take_profit: number;
  profit_pct: number;
  reward_risk: number;
  score: number;
}

export interface RadarView {
  running: boolean;
  phase: "idle" | "scanning" | "waiting" | "finished";
  source: "demo" | "binance" | null;
  interval_seconds: number | null;
  window_minutes: number | null;
  started_at: string | null;
  ends_at: string | null;
  next_scan_at: string | null;
  last_scan_at: string | null;
  last_error: string | null;
  scans: number;
  quiet: number;
  btc_name: string | null;
  btc_detail: string | null;
  universe: string[];
  active: RadarHit[];
  hits: RadarHit[];
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<T>;
}

export async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<T>;
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.detail)) {
      return payload.detail
        .map((item: { msg?: string }) => item.msg ?? "Dato no válido")
        .join(" ");
    }
  } catch {
    return "No se pudo completar la consulta.";
  }
  return "No se pudo completar la consulta.";
}
