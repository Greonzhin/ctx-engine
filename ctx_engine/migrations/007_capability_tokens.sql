CREATE TABLE IF NOT EXISTS capability_tokens (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  agent_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  workspace_id TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  note TEXT
);
