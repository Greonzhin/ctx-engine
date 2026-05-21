CREATE TABLE IF NOT EXISTS capsule_feedback (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  capsule_id TEXT NOT NULL,
  workspace_id TEXT,
  client_id TEXT NOT NULL,
  rating TEXT NOT NULL,
  useful_files_json TEXT NOT NULL DEFAULT '[]',
  missing_files_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT NOT NULL DEFAULT '',
  ledger_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_capsule_feedback_capsule_id
ON capsule_feedback(capsule_id);

CREATE INDEX IF NOT EXISTS idx_capsule_feedback_workspace_id
ON capsule_feedback(workspace_id);
