CREATE TABLE IF NOT EXISTS crypto_snapshots (
    id INTEGER PRIMARY KEY,
    timestamp_utc DATETIME NOT NULL,
    venue VARCHAR(64) NOT NULL DEFAULT 'BINANCE',
    symbol VARCHAR(32) NOT NULL,
    spot_bid FLOAT,
    spot_ask FLOAT,
    futures_bid FLOAT,
    futures_ask FLOAT,
    mark_price FLOAT,
    index_price FLOAT,
    funding_rate FLOAT,
    next_funding_time_utc DATETIME,
    spot_spread FLOAT,
    futures_spread FLOAT,
    basis FLOAT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_crypto_snapshots_timestamp_utc ON crypto_snapshots(timestamp_utc);
CREATE INDEX IF NOT EXISTS ix_crypto_snapshots_symbol ON crypto_snapshots(symbol);

CREATE TABLE IF NOT EXISTS crypto_signals (
    id INTEGER PRIMARY KEY,
    timestamp_utc DATETIME NOT NULL,
    snapshot_id INTEGER,
    venue VARCHAR(64) NOT NULL DEFAULT 'BINANCE',
    symbol VARCHAR(32) NOT NULL,
    strategy VARCHAR(64) NOT NULL DEFAULT 'SPOT_PERP_CARRY',
    action VARCHAR(64) NOT NULL DEFAULT 'NO_TRADE',
    status VARCHAR(32) NOT NULL DEFAULT 'REJECTED',
    reason_code VARCHAR(128) NOT NULL,
    reason_es TEXT NOT NULL,
    reason_en TEXT NOT NULL,
    funding_rate FLOAT,
    daily_funding_estimate FLOAT,
    annualized_funding_estimate FLOAT,
    estimated_costs FLOAT,
    basis_risk FLOAT,
    net_daily_edge FLOAT,
    confidence FLOAT,
    recommended_notional FLOAT,
    max_notional FLOAT,
    raw_json TEXT NOT NULL,
    FOREIGN KEY(snapshot_id) REFERENCES crypto_snapshots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_crypto_signals_timestamp_utc ON crypto_signals(timestamp_utc);
CREATE INDEX IF NOT EXISTS ix_crypto_signals_snapshot_id ON crypto_signals(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_crypto_signals_symbol ON crypto_signals(symbol);
