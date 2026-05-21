CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  root_path TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  path TEXT NOT NULL,
  rel_path TEXT NOT NULL,
  language TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL,
  skeleton TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS symbols (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  file_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  signature TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  container TEXT,
  imports_json TEXT NOT NULL DEFAULT '[]',
  exports_json TEXT NOT NULL DEFAULT '[]',
  route_like INTEGER NOT NULL DEFAULT 0,
  test_name INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
  FOREIGN KEY(file_id) REFERENCES files(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
  symbol_id UNINDEXED,
  workspace_id UNINDEXED,
  name,
  kind,
  signature,
  path
);

CREATE TABLE IF NOT EXISTS docs (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  path TEXT NOT NULL,
  rel_path TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
  doc_id UNINDEXED,
  workspace_id UNINDEXED,
  title,
  body,
  path
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  claim TEXT NOT NULL,
  summary TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  trust_tier TEXT NOT NULL,
  linked_files_json TEXT NOT NULL DEFAULT '[]',
  linked_symbols_json TEXT NOT NULL DEFAULT '[]',
  linked_docs_json TEXT NOT NULL DEFAULT '[]',
  branch TEXT,
  created_at TEXT NOT NULL,
  last_verified_at TEXT,
  expires_at TEXT,
  superseded_by TEXT,
  evidence_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  memory_id UNINDEXED,
  workspace_id UNINDEXED,
  claim,
  summary,
  source
);

CREATE TABLE IF NOT EXISTS action_ledger (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  client_id TEXT NOT NULL,
  workspace_id TEXT,
  event_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS caches (
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  PRIMARY KEY(namespace, key)
);
