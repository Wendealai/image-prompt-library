ALTER TABLE prompt_templates ADD COLUMN quality_score REAL;
ALTER TABLE prompt_templates ADD COLUMN quality_label TEXT;
ALTER TABLE prompt_templates ADD COLUMN quality_reasons_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS prompt_image_generation_runs (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  generation_options_json TEXT NOT NULL DEFAULT '{}',
  references_json TEXT NOT NULL DEFAULT '[]',
  job_id TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  image_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompt_image_generation_runs_item ON prompt_image_generation_runs(item_id, created_at DESC);
