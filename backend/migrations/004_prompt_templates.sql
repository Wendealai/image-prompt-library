CREATE TABLE IF NOT EXISTS prompt_templates (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL UNIQUE,
  source_language TEXT NOT NULL,
  raw_text_snapshot TEXT NOT NULL,
  marked_text TEXT NOT NULL,
  slots_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN ('draft', 'ready', 'stale', 'failed')),
  analysis_confidence REAL,
  analysis_notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_item_status ON prompt_templates(item_id, status);

CREATE TABLE IF NOT EXISTS prompt_generation_sessions (
  id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  theme_keyword TEXT NOT NULL,
  accepted_variant_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(template_id) REFERENCES prompt_templates(id) ON DELETE CASCADE,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompt_generation_sessions_template ON prompt_generation_sessions(template_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_generation_sessions_item ON prompt_generation_sessions(item_id, created_at DESC);

CREATE TABLE IF NOT EXISTS prompt_generation_variants (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  iteration INTEGER NOT NULL,
  rendered_text TEXT NOT NULL,
  slot_values_json TEXT NOT NULL,
  segments_json TEXT NOT NULL,
  change_summary TEXT,
  accepted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES prompt_generation_sessions(id) ON DELETE CASCADE,
  UNIQUE(session_id, iteration)
);

CREATE INDEX IF NOT EXISTS idx_prompt_generation_variants_session ON prompt_generation_variants(session_id, iteration DESC);
