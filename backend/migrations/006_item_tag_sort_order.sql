ALTER TABLE item_tags ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;

UPDATE item_tags
SET sort_order = (
  SELECT COUNT(*)
  FROM item_tags earlier
  WHERE earlier.item_id = item_tags.item_id
    AND earlier.rowid <= item_tags.rowid
) - 1;
