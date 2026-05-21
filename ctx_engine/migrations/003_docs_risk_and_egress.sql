ALTER TABLE docs ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'clean';
ALTER TABLE docs ADD COLUMN risk_flags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE docs ADD COLUMN quarantined INTEGER NOT NULL DEFAULT 0;
ALTER TABLE docs ADD COLUMN scanned_at TEXT;

CREATE TABLE IF NOT EXISTS egress_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  workspace_id TEXT,
  library_id TEXT,
  query_hash TEXT NOT NULL,
  endpoint_host TEXT,
  status TEXT NOT NULL,
  latency_ms INTEGER NOT NULL,
  response_bytes INTEGER NOT NULL,
  cache_hit INTEGER NOT NULL DEFAULT 0,
  timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_egress_events_timestamp ON egress_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_egress_events_provider_timestamp ON egress_events(provider, timestamp DESC);
