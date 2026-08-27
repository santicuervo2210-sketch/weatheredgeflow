export type Language = "es" | "en";

export type Signal = {
  id: number;
  market_id: string;
  token_id?: string | null;
  question: string;
  city?: string | null;
  country?: string | null;
  target_date?: string | null;
  timezone?: string | null;
  weather_metric?: string | null;
  outcome?: string | null;
  side: string;
  action: string;
  status: string;
  reason_code: string;
  reason_es: string;
  reason_en: string;
  market_probability?: number | null;
  model_probability?: number | null;
  raw_edge?: number | null;
  net_edge?: number | null;
  confidence?: number | null;
  executable_price?: number | null;
  max_recommended_price?: number | null;
  best_bid?: number | null;
  best_ask?: number | null;
  spread?: number | null;
  liquidity_usd?: number | null;
  fee_rate?: number | null;
  estimated_fees?: number | null;
  spread_cost?: number | null;
  slippage?: number | null;
  uncertainty_penalty?: number | null;
  safety_margin?: number | null;
  gross_ev?: number | null;
  net_ev?: number | null;
  recommended_stake?: number | null;
  maximum_allowed_stake?: number | null;
  resolution_source?: string | null;
  resolution_station?: string | null;
  resolution_rules?: string | null;
  polymarket_url?: string | null;
  created_at_utc: string;
  distribution?: Record<string, number>;
  forecasts?: unknown[];
  observation?: Record<string, unknown>;
  risks?: Record<string, unknown>;
  data_freshness?: Record<string, string | null>;
};

export type DashboardData = {
  settings: Record<string, unknown>;
  runtime: Record<string, unknown>;
  system: {
    status: string;
    scheduler: { running: boolean; next_run_time?: string | null; scan_running: boolean };
  };
  latest_scan?: {
    id: number;
    status: string;
    mode: string;
    started_at_utc?: string | null;
    finished_at_utc?: string | null;
    next_scan_at_utc?: string | null;
    markets_found: number;
    weather_markets_found: number;
    supported_markets: number;
    opportunities_found: number;
    errors_count: number;
    duration_ms?: number | null;
    summary_es?: string | null;
    summary_en?: string | null;
  } | null;
  metrics: Record<string, number>;
  signals: Signal[];
  positions: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
  activity: Array<Record<string, unknown>>;
  bankroll_chart: Array<Record<string, unknown>>;
  analytics: Record<string, unknown>;
};

export async function fetchDashboard(): Promise<DashboardData> {
  return requestJson<DashboardData>("/api/dashboard");
}

export async function fetchSignal(id: number): Promise<Signal> {
  return requestJson<Signal>(`/api/signals/${id}`);
}

export async function runScan(): Promise<Record<string, unknown>> {
  return requestJson("/api/scan", { method: "POST" });
}

export async function updateSettings(updates: Record<string, unknown>, confirmed = false): Promise<Record<string, unknown>> {
  return requestJson("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates, confirmed })
  });
}

export async function updateControl(updates: { paused?: boolean; kill_switch?: boolean }): Promise<Record<string, unknown>> {
  return requestJson("/api/control", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates)
  });
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

