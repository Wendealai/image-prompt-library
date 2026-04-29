PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS prompt_templates_new (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL UNIQUE,
  source_language TEXT NOT NULL,
  raw_text_snapshot TEXT NOT NULL,
  marked_text TEXT NOT NULL,
  slots_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN ('draft', 'ready', 'stale', 'failed')),
  review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK(review_status IN ('pending_review', 'approved', 'rejected')),
  review_notes TEXT,
  reviewed_at TEXT,
  analysis_confidence REAL,
  analysis_notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

INSERT INTO prompt_templates_new (
  id,
  item_id,
  source_language,
  raw_text_snapshot,
  marked_text,
  slots_json,
  status,
  review_status,
  review_notes,
  reviewed_at,
  analysis_confidence,
  analysis_notes,
  created_at,
  updated_at
)
SELECT
  id,
  item_id,
  source_language,
  raw_text_snapshot,
  marked_text,
  slots_json,
  status,
  CASE WHEN status = 'ready' THEN 'approved' ELSE 'pending_review' END,
  NULL,
  NULL,
  analysis_confidence,
  analysis_notes,
  created_at,
  updated_at
FROM prompt_templates;

DROP TABLE prompt_templates;
ALTER TABLE prompt_templates_new RENAME TO prompt_templates;

CREATE INDEX IF NOT EXISTS idx_prompt_templates_item_status ON prompt_templates(item_id, status);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_review_status ON prompt_templates(review_status, status);

PRAGMA foreign_keys = ON;
