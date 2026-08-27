CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY,
    event_id TEXT,
    market_id TEXT NOT NULL UNIQUE,
    condition_id TEXT,
    question TEXT NOT NULL,
    slug TEXT,
    category TEXT,
    polymarket_url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    closed INTEGER NOT NULL DEFAULT 0,
    end_date_utc DATETIME,
    raw_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS market_outcomes (
    id INTEGER PRIMARY KEY,
    market_ref_id INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'YES',
    lower_bound REAL,
    upper_bound REAL,
    unit TEXT,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_market_outcome_token UNIQUE (market_id, token_id)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    started_at_utc DATETIME NOT NULL,
    finished_at_utc DATETIME,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    mode TEXT NOT NULL DEFAULT 'PAPER',
    markets_found INTEGER NOT NULL DEFAULT 0,
    weather_markets_found INTEGER NOT NULL DEFAULT 0,
    supported_markets INTEGER NOT NULL DEFAULT 0,
    opportunities_found INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    next_scan_at_utc DATETIME,
    summary_es TEXT,
    summary_en TEXT
);

CREATE TABLE IF NOT EXISTS weather_forecasts (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT,
    timezone TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    weather_metric TEXT NOT NULL,
    target_date TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    issued_at_utc DATETIME,
    fetched_at_utc DATETIME NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_observations (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    station TEXT,
    observed_max REAL,
    observed_min REAL,
    current_temperature REAL,
    unit TEXT NOT NULL,
    observed_at_utc DATETIME,
    fetched_at_utc DATETIME NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY,
    scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    token_id TEXT,
    event_id TEXT,
    question TEXT NOT NULL,
    city TEXT,
    country TEXT,
    target_date TEXT,
    timezone TEXT,
    weather_metric TEXT,
    outcome TEXT,
    side TEXT NOT NULL DEFAULT 'BUY_YES',
    action TEXT NOT NULL DEFAULT 'NO_TRADE',
    status TEXT NOT NULL DEFAULT 'REJECTED',
    reason_code TEXT NOT NULL,
    reason_es TEXT NOT NULL,
    reason_en TEXT NOT NULL,
    market_probability REAL,
    model_probability REAL,
    raw_edge REAL,
    net_edge REAL,
    confidence REAL,
    executable_price REAL,
    max_recommended_price REAL,
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    liquidity_usd REAL,
    fee_rate REAL,
    estimated_fees REAL,
    spread_cost REAL,
    slippage REAL,
    uncertainty_penalty REAL,
    safety_margin REAL,
    gross_ev REAL,
    net_ev REAL,
    recommended_stake REAL,
    maximum_allowed_stake REAL,
    resolution_source TEXT,
    resolution_station TEXT,
    resolution_rules TEXT,
    polymarket_url TEXT,
    distribution_json TEXT,
    forecasts_json TEXT,
    observation_json TEXT,
    risks_json TEXT,
    data_freshness_json TEXT,
    created_at_utc DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    order_timestamp_utc DATETIME NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    requested_price REAL NOT NULL,
    simulated_fill_price REAL,
    stake_usd REAL NOT NULL,
    shares REAL,
    fees REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    pnl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES paper_orders(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    event_id TEXT,
    outcome TEXT NOT NULL,
    entry_price REAL NOT NULL,
    shares REAL NOT NULL,
    stake_usd REAL NOT NULL,
    fees REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    opened_at_utc DATETIME NOT NULL,
    resolved_at_utc DATETIME,
    gross_pnl REAL NOT NULL DEFAULT 0,
    net_pnl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS resolutions (
    id INTEGER PRIMARY KEY,
    market_id TEXT NOT NULL,
    winning_token_id TEXT,
    winning_outcome TEXT,
    resolved_at_utc DATETIME NOT NULL,
    source TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bankroll_snapshots (
    id INTEGER PRIMARY KEY,
    timestamp_utc DATETIME NOT NULL,
    mode TEXT NOT NULL DEFAULT 'PAPER',
    bankroll REAL NOT NULL,
    cash REAL NOT NULL,
    open_exposure REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    drawdown REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY,
    timestamp_utc DATETIME NOT NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    category TEXT NOT NULL DEFAULT 'SYSTEM',
    message_es TEXT NOT NULL,
    message_en TEXT NOT NULL,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS ix_markets_event_id ON markets(event_id);
CREATE INDEX IF NOT EXISTS ix_markets_market_id ON markets(market_id);
CREATE INDEX IF NOT EXISTS ix_markets_condition_id ON markets(condition_id);
CREATE INDEX IF NOT EXISTS ix_market_outcomes_market_id ON market_outcomes(market_id);
CREATE INDEX IF NOT EXISTS ix_market_outcomes_token_id ON market_outcomes(token_id);
CREATE INDEX IF NOT EXISTS ix_scans_started_at_utc ON scans(started_at_utc);
CREATE INDEX IF NOT EXISTS ix_signals_scan_id ON signals(scan_id);
CREATE INDEX IF NOT EXISTS ix_signals_market_id ON signals(market_id);
CREATE INDEX IF NOT EXISTS ix_signals_token_id ON signals(token_id);
CREATE INDEX IF NOT EXISTS ix_signals_event_id ON signals(event_id);
CREATE INDEX IF NOT EXISTS ix_signals_created_at_utc ON signals(created_at_utc);
CREATE INDEX IF NOT EXISTS ix_paper_orders_signal_id ON paper_orders(signal_id);
CREATE INDEX IF NOT EXISTS ix_paper_orders_market_id ON paper_orders(market_id);
CREATE INDEX IF NOT EXISTS ix_paper_orders_token_id ON paper_orders(token_id);
CREATE INDEX IF NOT EXISTS ix_paper_positions_order_id ON paper_positions(order_id);
CREATE INDEX IF NOT EXISTS ix_paper_positions_market_id ON paper_positions(market_id);
CREATE INDEX IF NOT EXISTS ix_paper_positions_token_id ON paper_positions(token_id);
CREATE INDEX IF NOT EXISTS ix_paper_positions_event_id ON paper_positions(event_id);
CREATE INDEX IF NOT EXISTS ix_resolutions_market_id ON resolutions(market_id);
CREATE INDEX IF NOT EXISTS ix_bankroll_snapshots_timestamp_utc ON bankroll_snapshots(timestamp_utc);
CREATE INDEX IF NOT EXISTS ix_system_events_timestamp_utc ON system_events(timestamp_utc);

