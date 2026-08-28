import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  ExternalLink,
  Gauge,
  Globe2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  Bitcoin,
  Zap,
  Target
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { CryptoSignal, DashboardData, Language, RadarItem, Signal, fetchDashboard, fetchSignal, runCryptoScan, runScan, updateControl, updateSettings } from "./api";

const copy = {
  es: {
    nav: ["Radar", "Oportunidades", "Crypto", "Cartera", "Rendimiento", "Actividad", "Settings"],
    mode: "MODO",
    status: "STATUS",
    lastScan: "ÚLTIMO SCAN",
    nextScan: "PRÓXIMO SCAN",
    bankroll: "BANKROLL",
    todayPnl: "PNL HOY",
    totalPnl: "PNL TOTAL",
    roi: "ROI",
    exposure: "EXPOSICIÓN",
    scanNow: "Analizar ahora",
    pause: "PAUSAR BOT",
    resume: "REANUDAR",
    kill: "KILL SWITCH",
    market: "Mercado",
    city: "Ciudad",
    date: "Fecha",
    outcome: "Outcome",
    price: "Precio",
    marketProb: "Prob. mercado",
    modelProb: "Prob. modelo",
    rawEdge: "Edge bruto",
    netEdge: "Edge neto",
    confidence: "Confidence",
    stake: "Stake",
    state: "Estado",
    details: "Detalle",
    openPoly: "ABRIR MERCADO",
    forecasts: "Pronósticos",
    observations: "Observaciones",
    risks: "Riesgos",
    settingsSaved: "Settings guardados",
    save: "Guardar",
    cash: "Cash",
    realized: "Realized PnL",
    unrealized: "Unrealized PnL",
    drawdown: "Max drawdown",
    winRate: "Win rate",
    profitFactor: "Profit factor",
    trades: "Trades",
    noRows: "Sin registros todavía",
    signalReason: "Razón",
    firstRun: "Analizando mercados..."
  },
  en: {
    nav: ["Radar", "Opportunities", "Crypto", "Portfolio", "Analytics", "Activity", "Settings"],
    mode: "MODE",
    status: "STATUS",
    lastScan: "LAST SCAN",
    nextScan: "NEXT SCAN",
    bankroll: "BANKROLL",
    todayPnl: "TODAY PNL",
    totalPnl: "TOTAL PNL",
    roi: "ROI",
    exposure: "OPEN EXPOSURE",
    scanNow: "Scan now",
    pause: "PAUSE BOT",
    resume: "RESUME",
    kill: "KILL SWITCH",
    market: "Market",
    city: "City",
    date: "Date",
    outcome: "Outcome",
    price: "Price",
    marketProb: "Market prob.",
    modelProb: "Model prob.",
    rawEdge: "Raw edge",
    netEdge: "Net edge",
    confidence: "Confidence",
    stake: "Stake",
    state: "State",
    details: "Detail",
    openPoly: "OPEN MARKET",
    forecasts: "Forecasts",
    observations: "Observations",
    risks: "Risks",
    settingsSaved: "Settings saved",
    save: "Save",
    cash: "Cash",
    realized: "Realized PnL",
    unrealized: "Unrealized PnL",
    drawdown: "Max drawdown",
    winRate: "Win rate",
    profitFactor: "Profit factor",
    trades: "Trades",
    noRows: "No records yet",
    signalReason: "Reason",
    firstRun: "Scanning markets..."
  }
};

type Page = "radar" | "opportunities" | "crypto" | "portfolio" | "analytics" | "activity" | "settings";

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>("radar");
  const [language, setLanguage] = useState<Language>((localStorage.getItem("weatheredgeflow.language") as Language) || "es");
  const [selected, setSelected] = useState<Signal | null>(null);
  const t = copy[language];

  const load = async () => {
    try {
      const payload = await fetchDashboard();
      setData(payload);
      const remoteLanguage = payload.settings.language === "en" ? "en" : "es";
      setLanguage(remoteLanguage);
      localStorage.setItem("weatheredgeflow.language", remoteLanguage);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const nav = [
    { id: "radar" as Page, icon: Target, label: t.nav[0] },
    { id: "opportunities" as Page, icon: Zap, label: t.nav[1] },
    { id: "crypto" as Page, icon: Bitcoin, label: t.nav[2] },
    { id: "portfolio" as Page, icon: BriefcaseBusiness, label: t.nav[3] },
    { id: "analytics" as Page, icon: BarChart3, label: t.nav[4] },
    { id: "activity" as Page, icon: Activity, label: t.nav[5] },
    { id: "settings" as Page, icon: Settings, label: t.nav[6] }
  ];

  if (loading && !data) {
    return <div className="boot">{t.firstRun}</div>;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Gauge size={18} /></div>
          <div>
            <strong>WEATHEREDGE</strong>
            <span>WeatherEdgeflow</span>
          </div>
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)} title={item.label}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <h1>WEATHEREDGE</h1>
            <p>{data?.latest_scan?.[language === "es" ? "summary_es" : "summary_en"] || t.firstRun}</p>
          </div>
          <div className="actions">
            <div className="segment">
              <button className={language === "es" ? "selected" : ""} onClick={() => changeLanguage("es", setLanguage, load)}>ES</button>
              <button className={language === "en" ? "selected" : ""} onClick={() => changeLanguage("en", setLanguage, load)}>EN</button>
            </div>
            <button className="icon-button" title={t.scanNow} onClick={async () => { await runScan(); await load(); }}>
              <RefreshCw size={18} />
            </button>
            <button
              className="control"
              onClick={async () => {
                await updateControl({ paused: !(data?.settings.paused as boolean) });
                await load();
              }}
            >
              {(data?.settings.paused as boolean) ? <PlayCircle size={18} /> : <PauseCircle size={18} />}
              <span>{(data?.settings.paused as boolean) ? t.resume : t.pause}</span>
            </button>
            <button
              className={(data?.settings.kill_switch as boolean) ? "danger enabled" : "danger"}
              onClick={async () => {
                await updateControl({ kill_switch: !(data?.settings.kill_switch as boolean) });
                await load();
              }}
            >
              <ShieldAlert size={18} />
              <span>{t.kill}</span>
            </button>
          </div>
        </header>

        {error && <div className="alert">{error}</div>}
        {data && <Kpis data={data} t={t} />}

        <section className="content">
          {data && page === "radar" && <MarketRadarPanel data={data} language={language} load={load} />}
          {data && page === "opportunities" && <Opportunities data={data} t={t} language={language} onSelect={async (signal) => setSelected(await fetchSignal(signal.id))} />}
          {data && page === "crypto" && <CryptoPanel data={data} language={language} load={load} />}
          {data && page === "portfolio" && <Portfolio data={data} t={t} />}
          {data && page === "analytics" && <Analytics data={data} t={t} />}
          {data && page === "activity" && <ActivityLog data={data} language={language} t={t} />}
          {data && page === "settings" && <SettingsPage data={data} t={t} load={load} />}
        </section>
      </main>

      {selected && <SignalDetail signal={selected} t={t} language={language} onClose={() => setSelected(null)} />}
    </div>
  );
}

function MarketRadarPanel({ data, language, load }: { data: DashboardData; language: Language; load: () => Promise<void> }) {
  const radar = data.market_radar;
  const best = radar.best || radar.best_watchlist;
  return (
    <div className="radar-layout">
      <div className={radar.status === "OPPORTUNITY" ? "radar-hero opportunity" : "radar-hero no-trade"}>
        <div>
          <span className="eyebrow">MULTI-MARKET RADAR</span>
          <h2>{radar.status === "OPPORTUNITY" ? "OPPORTUNITY" : "NO TRADE"}</h2>
          <p>{language === "es" ? radar.summary_es : radar.summary_en}</p>
        </div>
        <div className="radar-actions">
          <button className="primary" onClick={async () => { await Promise.all([runScan(), runCryptoScan()]); await load(); }}>
            <RefreshCw size={18} />
            <span>{language === "es" ? "Escanear todo" : "Scan all"}</span>
          </button>
          {best?.url && (
            <a className="poly-link" href={best.url} target="_blank" rel="noreferrer">
              <ExternalLink size={18} />
              <span>{language === "es" ? "Abrir mercado" : "Open market"}</span>
            </a>
          )}
        </div>
      </div>

      {best && (
        <div className="panel radar-best">
          <h2>{language === "es" ? "Mejor lectura ahora" : "Best read now"}</h2>
          <div className="detail-grid">
            <Info label="Source" value={`${best.source.toUpperCase()} / ${best.venue}`} />
            <Info label="Instrument" value={best.instrument} />
            <Info label="Action" value={best.action} />
            <Info label="Status" value={best.status} />
            <Info label="Model prob." value={pct(best.model_probability)} />
            <Info label="Market prob." value={pct(best.market_probability)} />
            <Info label="Net edge" value={pct(best.net_edge)} />
            <Info label="Confidence" value={score(best.confidence)} />
            <Info label="Size" value={usd(best.recommended_size)} />
            <Info label="Score" value={best.score.toFixed(2)} />
            <Info label="Reason" value={language === "es" ? best.reason_es : best.reason_en} wide />
            <Info label="Market" value={best.market} wide />
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-head">
          <h2>{language === "es" ? "Ranking cross-market" : "Cross-market ranking"}</h2>
          <span className="muted">{radar.actionable_count}/{radar.candidate_count}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Venue</th>
                <th>Market</th>
                <th>Action</th>
                <th>Status</th>
                <th>Model</th>
                <th>Market</th>
                <th>Net edge</th>
                <th>Confidence</th>
                <th>Size</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {radar.items.length === 0 && <EmptyRow colSpan={11} text="-" />}
              {radar.items.map((item) => <RadarRow key={`${item.source}-${item.id}`} item={item} language={language} />)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RadarRow({ item, language }: { item: RadarItem; language: Language }) {
  return (
    <tr className={rowTone(item.status)}>
      <td>{item.source}</td>
      <td>{item.venue}</td>
      <td className="market-cell">{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.market}</a> : item.market}</td>
      <td>{item.action}</td>
      <td><span className="badge">{item.status}</span></td>
      <td>{pct(item.model_probability)}</td>
      <td>{pct(item.market_probability)}</td>
      <td>{pct(item.net_edge)}</td>
      <td>{score(item.confidence)}</td>
      <td>{usd(item.recommended_size)}</td>
      <td className="market-cell">{language === "es" ? item.reason_es : item.reason_en}</td>
    </tr>
  );
}

function Kpis({ data, t }: { data: DashboardData; t: typeof copy.es }) {
  const metrics = data.metrics;
  const kpis = [
    [t.mode, String(data.settings.mode || "PAPER")],
    [t.status, data.system.status],
    [t.lastScan, formatTime(data.latest_scan?.finished_at_utc)],
    [t.nextScan, formatTime(data.latest_scan?.next_scan_at_utc || data.system.scheduler.next_run_time)],
    [t.bankroll, usd(metrics.bankroll)],
    [t.todayPnl, usd(metrics.today_pnl)],
    [t.totalPnl, usd(metrics.realized_pnl)],
    [t.roi, pct(metrics.roi)],
    [t.exposure, usd(metrics.open_exposure)]
  ];
  return (
    <section className="kpis">
      {kpis.map(([label, value]) => (
        <div className="kpi" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

function Opportunities({ data, t, language, onSelect }: { data: DashboardData; t: typeof copy.es; language: Language; onSelect: (signal: Signal) => void }) {
  return (
    <div className="panel">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t.market}</th>
              <th>{t.city}</th>
              <th>{t.date}</th>
              <th>{t.outcome}</th>
              <th>{t.price}</th>
              <th>{t.marketProb}</th>
              <th>{t.modelProb}</th>
              <th>{t.rawEdge}</th>
              <th>{t.netEdge}</th>
              <th>{t.confidence}</th>
              <th>{t.stake}</th>
              <th>{t.state}</th>
            </tr>
          </thead>
          <tbody>
            {data.signals.length === 0 && <EmptyRow colSpan={12} text={t.noRows} />}
            {data.signals.map((signal) => (
              <tr key={signal.id} onClick={() => onSelect(signal)} className={rowTone(signal.status)}>
                <td className="market-cell">{signal.question}</td>
                <td>{signal.city || "-"}</td>
                <td>{signal.target_date || "-"}</td>
                <td>{signal.outcome || "-"}</td>
                <td>{moneyProb(signal.executable_price)}</td>
                <td>{pct(signal.market_probability)}</td>
                <td>{pct(signal.model_probability)}</td>
                <td>{pct(signal.raw_edge)}</td>
                <td>{pct(signal.net_edge)}</td>
                <td>{score(signal.confidence)}</td>
                <td>{usd(signal.recommended_stake)}</td>
                <td><span className="badge">{statusText(signal, language)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CryptoPanel({ data, language, load }: { data: DashboardData; language: Language; load: () => Promise<void> }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{language === "es" ? "Crypto Signals" : "Crypto Signals"}</h2>
        <button className="primary" onClick={async () => { await runCryptoScan(); await load(); }}>
          <RefreshCw size={18} />
          <span>{language === "es" ? "Analizar crypto" : "Scan crypto"}</span>
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Action</th>
              <th>Status</th>
              <th>Funding</th>
              <th>Model prob.</th>
              <th>Market prob.</th>
              <th>Raw edge</th>
              <th>Daily est.</th>
              <th>Costs</th>
              <th>Basis risk</th>
              <th>Net daily edge</th>
              <th>Confidence</th>
              <th>Notional</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {(data.crypto_signals || []).length === 0 && <EmptyRow colSpan={14} text="-" />}
            {(data.crypto_signals || []).map((signal: CryptoSignal) => (
              <tr key={signal.id} className={rowTone(signal.status)}>
                <td>{signal.symbol}</td>
                <td>{signal.action}</td>
                <td><span className="badge">{signal.status}</span></td>
                <td>{pct(signal.funding_rate)}</td>
                <td>{pct(signal.model_probability)}</td>
                <td>{pct(signal.market_probability)}</td>
                <td>{pct(signal.raw_edge)}</td>
                <td>{pct(signal.daily_funding_estimate)}</td>
                <td>{pct(signal.estimated_costs)}</td>
                <td>{pct(signal.basis_risk)}</td>
                <td>{pct(signal.net_daily_edge)}</td>
                <td>{score(signal.confidence)}</td>
                <td>{usd(signal.recommended_notional)}</td>
                <td className="market-cell">{language === "es" ? signal.reason_es : signal.reason_en}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Portfolio({ data, t }: { data: DashboardData; t: typeof copy.es }) {
  const metrics = data.metrics;
  const statRows = [
    [t.bankroll, usd(metrics.initial_bankroll)],
    [t.cash, usd(metrics.cash)],
    [t.exposure, usd(metrics.open_exposure)],
    [t.realized, usd(metrics.realized_pnl)],
    [t.unrealized, usd(metrics.unrealized_pnl)],
    [t.roi, pct(metrics.roi)],
    [t.drawdown, `${Number(metrics.max_drawdown || 0).toFixed(2)}%`],
    [t.winRate, pct(metrics.win_rate)],
    [t.profitFactor, Number(metrics.profit_factor || 0).toFixed(2)],
    [t.trades, String(metrics.number_of_trades || 0)]
  ];
  return (
    <div className="grid-two">
      <div className="panel">
        <h2>{t.nav[3]}</h2>
        <div className="metric-list">
          {statRows.map(([label, value]) => (
            <div key={label}><span>{label}</span><strong>{value}</strong></div>
          ))}
        </div>
      </div>
      <div className="panel chart">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.bankroll_chart}>
            <CartesianGrid stroke="#1d3340" />
            <XAxis dataKey="timestamp_utc" tickFormatter={formatShortTime} stroke="#7b93a1" />
            <YAxis stroke="#7b93a1" />
            <Tooltip contentStyle={{ background: "#09131a", border: "1px solid #244050" }} />
            <Line type="monotone" dataKey="bankroll" stroke="#4ddf9a" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="open_exposure" stroke="#f2bc57" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <PositionsTable title="Open positions" rows={data.positions.filter((p) => p.status === "OPEN")} />
      <PositionsTable title="History" rows={data.positions.filter((p) => p.status !== "OPEN")} />
    </div>
  );
}

function PositionsTable({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Market</th><th>Outcome</th><th>Entry</th><th>Stake</th><th>Shares</th><th>Status</th><th>PnL</th></tr></thead>
          <tbody>
            {rows.length === 0 && <EmptyRow colSpan={7} text="-" />}
            {rows.map((row) => (
              <tr key={String(row.id)}>
                <td className="market-cell">{String(row.market_id)}</td>
                <td>{String(row.outcome)}</td>
                <td>{moneyProb(row.entry_price as number)}</td>
                <td>{usd(row.stake_usd as number)}</td>
                <td>{Number(row.shares || 0).toFixed(3)}</td>
                <td><span className="badge">{String(row.status)}</span></td>
                <td>{usd(row.net_pnl as number)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Analytics({ data, t }: { data: DashboardData; t: typeof copy.es }) {
  const analytics = data.analytics;
  const cards: Array<[string, string | number]> = [
    ["Total signals", Number(analytics.total_signals || 0)],
    ["Paper trades", Number(analytics.paper_trades || 0)],
    ["Wins", Number(analytics.wins || 0)],
    ["Losses", Number(analytics.losses || 0)],
    ["Average edge", pct(analytics.average_edge as number)],
    ["Average return", pct(analytics.average_realized_return as number)],
    ["Brier score", analytics.brier_score === null || analytics.brier_score === undefined ? "-" : String(analytics.brier_score)]
  ];
  return (
    <div className="grid-two">
      <div className="panel">
        <h2>{t.nav[4]}</h2>
        <div className="metric-list">
          {cards.map(([label, value]) => <div key={String(label)}><span>{label}</span><strong>{String(value)}</strong></div>)}
        </div>
      </div>
      <BarPanel title="Calibration" data={(analytics.calibration as Array<Record<string, unknown>>) || []} x="bucket" y="count" />
      <BarPanel title="Results by city" data={(analytics.results_by_city as Array<Record<string, unknown>>) || []} x="city" y="signals" />
      <BarPanel title="Edge buckets" data={(analytics.results_by_edge_bucket as Array<Record<string, unknown>>) || []} x="bucket" y="count" />
    </div>
  );
}

function BarPanel({ title, data, x, y }: { title: string; data: Array<Record<string, unknown>>; x: string; y: string }) {
  return (
    <div className="panel chart">
      <h2>{title}</h2>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <CartesianGrid stroke="#1d3340" />
          <XAxis dataKey={x} stroke="#7b93a1" />
          <YAxis stroke="#7b93a1" allowDecimals={false} />
          <Tooltip contentStyle={{ background: "#09131a", border: "1px solid #244050" }} />
          <Bar dataKey={y} fill="#4ddf9a" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ActivityLog({ data, language, t }: { data: DashboardData; language: Language; t: typeof copy.es }) {
  return (
    <div className="panel log">
      <h2>{t.nav[5]}</h2>
      {data.activity.length === 0 && <p>{t.noRows}</p>}
      {data.activity.map((event) => (
        <div className={`log-row ${String(event.level).toLowerCase()}`} key={String(event.id)}>
          <time>{formatTime(String(event.timestamp_utc))}</time>
          <span>{String(event[language === "es" ? "message_es" : "message_en"])}</span>
        </div>
      ))}
    </div>
  );
}

function SettingsPage({ data, t, load }: { data: DashboardData; t: typeof copy.es; load: () => Promise<void> }) {
  const [form, setForm] = useState<Record<string, unknown>>(data.settings);
  useEffect(() => setForm(data.settings), [data.settings]);
  const fields = [
    ["venue", "Venue", "select", ["KALSHI", "POLYMARKET"]],
    ["mode", "Mode", "select", ["OBSERVE", "PAPER", "LIVE_SIGNAL"]],
    ["bankroll_usd", "Bankroll", "number"],
    ["paper_bankroll_usd", "Paper bankroll", "number"],
    ["scan_interval_minutes", "Scan interval", "number"],
    ["min_net_edge", "Minimum edge", "number"],
    ["max_position_usd", "Maximum stake", "number"],
    ["max_position_percent", "Max position %", "number"],
    ["max_total_exposure_percent", "Max exposure %", "number"],
    ["max_daily_loss_percent", "Daily loss limit %", "number"],
    ["max_drawdown_percent", "Drawdown limit %", "number"],
    ["min_confidence", "Minimum confidence", "number"],
    ["max_spread", "Maximum spread", "number"],
    ["preferred_horizon_hours", "Preferred horizon", "number"],
    ["user_timezone", "Timezone", "text"],
    ["alert_email_recipient", "Alert email", "text"],
    ["alert_min_confidence", "Alert min confidence", "number"],
    ["alert_min_net_edge", "Alert min edge", "number"],
    ["alert_min_model_probability", "Alert min probability", "number"],
    ["alert_min_profit_usd_per_1", "Alert min profit / $1", "number"]
  ] as const;
  return (
    <div className="panel settings-panel">
      <h2><SlidersHorizontal size={18} /> {t.nav[6]}</h2>
      <div className="settings-grid">
        <label className="checkbox-field">
          <span>Email alerts</span>
          <input
            type="checkbox"
            checked={Boolean(form.alert_email_enabled)}
            onChange={(e) => setForm({ ...form, alert_email_enabled: e.target.checked })}
          />
        </label>
        <label>
          <span>Language</span>
          <select value={String(form.language)} onChange={(e) => setForm({ ...form, language: e.target.value })}>
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </label>
        {fields.map(([key, label, type, options]) => (
          <label key={key}>
            <span>{label}</span>
            {type === "select" ? (
              <select value={String(form[key])} onChange={(e) => setForm({ ...form, [key]: e.target.value })}>
                {options?.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            ) : (
              <input
                type={type}
                value={String(form[key] ?? "")}
                step={key.includes("edge") || key.includes("spread") ? "0.01" : "1"}
                onChange={(e) => setForm({ ...form, [key]: type === "number" ? Number(e.target.value) : e.target.value })}
              />
            )}
          </label>
        ))}
      </div>
      <button
        className="primary"
        onClick={async () => {
          const ok = window.confirm("Confirm settings update");
          await updateSettings(form, ok);
          await load();
        }}
      >
        <Settings size={18} />
        <span>{t.save}</span>
      </button>
    </div>
  );
}

function SignalDetail({ signal, t, language, onClose }: { signal: Signal; t: typeof copy.es; language: Language; onClose: () => void }) {
  const probabilityBars = useMemo(() => {
    const rows = Object.entries(signal.distribution || {}).map(([temperature, probability]) => ({ temperature, probability: probability * 100 }));
    return rows.sort((a, b) => Number(a.temperature) - Number(b.temperature));
  }, [signal]);
  const compare = [
    { name: "Market", probability: (signal.market_probability || 0) * 100 },
    { name: "Model", probability: (signal.model_probability || 0) * 100 }
  ];
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{t.details}</h2>
            <p>{signal.question}</p>
          </div>
          <button className="icon-button" onClick={onClose}>×</button>
        </div>
        <div className="detail-grid">
          <Info label={t.signalReason} value={language === "es" ? signal.reason_es : signal.reason_en} wide />
          <Info label="URL" value={signal.polymarket_url || "-"} wide />
          <Info label="Resolution" value={signal.resolution_rules || "-"} wide />
          <Info label="Station" value={signal.resolution_station || "-"} />
          <Info label="YES / NO" value={`${moneyProb(signal.best_ask)} / ${moneyProb(signal.best_bid)}`} />
          <Info label="Spread" value={moneyProb(signal.spread)} />
          <Info label="Liquidity" value={usd(signal.liquidity_usd)} />
          <Info label="Raw edge" value={pct(signal.raw_edge)} />
          <Info label="Fees" value={usd(signal.estimated_fees)} />
          <Info label="Slippage" value={pct(signal.slippage)} />
          <Info label="Uncertainty" value={pct(signal.uncertainty_penalty)} />
          <Info label="Net edge" value={pct(signal.net_edge)} />
          <Info label="Confidence" value={score(signal.confidence)} />
          <Info label="Stake" value={usd(signal.recommended_stake)} />
        </div>
        {signal.polymarket_url && (
          <a className="poly-link" href={signal.polymarket_url} target="_blank" rel="noreferrer">
            <ExternalLink size={18} />
            <span>{t.openPoly}</span>
          </a>
        )}
        <div className="grid-two">
          <div className="panel chart">
            <h2>{t.marketProb} vs {t.modelProb}</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={compare}>
                <CartesianGrid stroke="#1d3340" />
                <XAxis dataKey="name" stroke="#7b93a1" />
                <YAxis stroke="#7b93a1" domain={[0, 100]} />
                <Tooltip contentStyle={{ background: "#09131a", border: "1px solid #244050" }} />
                <Bar dataKey="probability" fill="#4ddf9a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="panel chart">
            <h2>Temperature distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={probabilityBars}>
                <CartesianGrid stroke="#1d3340" />
                <XAxis dataKey="temperature" stroke="#7b93a1" />
                <YAxis stroke="#7b93a1" />
                <Tooltip contentStyle={{ background: "#09131a", border: "1px solid #244050" }} />
                <Bar dataKey="probability" fill="#60a5fa" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <JsonBlock title={t.forecasts} value={signal.forecasts || []} />
        <JsonBlock title={t.observations} value={signal.observation || {}} />
        <JsonBlock title={t.risks} value={signal.risks || {}} />
      </div>
    </div>
  );
}

function Info({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return <div className={wide ? "info wide" : "info"}><span>{label}</span><strong>{value}</strong></div>;
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return <details><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return <tr><td colSpan={colSpan} className="empty">{text}</td></tr>;
}

async function changeLanguage(language: Language, setLanguage: (value: Language) => void, load: () => Promise<void>) {
  setLanguage(language);
  localStorage.setItem("weatheredgeflow.language", language);
  await updateSettings({ language }, true);
  await load();
}

function rowTone(status: string) {
  if (status === "OPPORTUNITY") return "opportunity";
  if (status === "OBSERVE") return "observe";
  return "rejected";
}

function statusText(signal: Signal, language: Language) {
  if (signal.status === "OPPORTUNITY") return signal.action;
  if (signal.status === "OBSERVE") return "WATCH";
  return language === "es" ? "NO TRADE" : "NO TRADE";
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatShortTime(value: unknown) {
  if (!value) return "";
  return new Date(String(value)).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function pct(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function score(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Number(value).toFixed(0)}/100`;
}

function usd(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `$${Number(value).toFixed(2)}`;
}

function moneyProb(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `$${Number(value).toFixed(3)}`;
}
