ALTER TABLE memories ADD COLUMN lifecycle_tier TEXT NOT NULL DEFAULT 'warm';
ALTER TABLE memories ADD COLUMN agent_namespace TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_memories_workspace_scope_tier
  ON memories(workspace_id, scope, lifecycle_tier, created_at DESC);
