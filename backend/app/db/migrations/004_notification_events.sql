CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY,
    dedupe_key VARCHAR(256) NOT NULL UNIQUE,
    signal_type VARCHAR(32) NOT NULL,
    signal_id INTEGER,
    recipient VARCHAR(320) NOT NULL,
    channel VARCHAR(32) NOT NULL DEFAULT 'EMAIL',
    subject VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    error TEXT,
    created_at_utc DATETIME NOT NULL,
    sent_at_utc DATETIME
);

CREATE INDEX IF NOT EXISTS ix_notification_events_dedupe_key ON notification_events(dedupe_key);
CREATE INDEX IF NOT EXISTS ix_notification_events_signal_id ON notification_events(signal_id);
CREATE INDEX IF NOT EXISTS ix_notification_events_created_at_utc ON notification_events(created_at_utc);
