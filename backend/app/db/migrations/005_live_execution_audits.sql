CREATE TABLE IF NOT EXISTS live_execution_audits (
    id INTEGER PRIMARY KEY,
    created_at_utc DATETIME NOT NULL,
    source VARCHAR(32) NOT NULL,
    signal_id INTEGER,
    venue VARCHAR(64) NOT NULL,
    instrument VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL,
    order_type VARCHAR(32) NOT NULL DEFAULT 'LIMIT',
    limit_price FLOAT,
    stake_usd FLOAT,
    stop_loss_price FLOAT,
    status VARCHAR(32) NOT NULL DEFAULT 'BLOCKED',
    reason_code VARCHAR(128) NOT NULL,
    reason_es TEXT NOT NULL,
    reason_en TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_live_execution_audits_created_at_utc ON live_execution_audits(created_at_utc);
CREATE INDEX IF NOT EXISTS ix_live_execution_audits_signal_id ON live_execution_audits(signal_id);
