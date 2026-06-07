ALTER TABLE items ADD COLUMN use_case TEXT;

CREATE INDEX IF NOT EXISTS idx_items_use_case ON items(use_case);
