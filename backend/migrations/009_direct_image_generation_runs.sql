ALTER TABLE prompt_image_generation_runs ADD COLUMN source TEXT NOT NULL DEFAULT 'workflow';
ALTER TABLE prompt_image_generation_runs ADD COLUMN batch_id TEXT;
ALTER TABLE prompt_image_generation_runs ADD COLUMN error_code TEXT;
ALTER TABLE prompt_image_generation_runs ADD COLUMN error_message TEXT;
ALTER TABLE prompt_image_generation_runs ADD COLUMN error_details_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_prompt_image_generation_runs_batch ON prompt_image_generation_runs(item_id, batch_id, created_at DESC);
