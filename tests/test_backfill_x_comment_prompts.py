from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, PromptIn

ROOT = Path(__file__).resolve().parents[1]


def load_backfill():
    path = ROOT / "scripts" / "backfill-x-comment-prompts.py"
    spec = importlib.util.spec_from_file_location("backfill_x_comment_prompts_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_backfill_updates_existing_x_prompt_from_thread(monkeypatch, tmp_path):
    backfill = load_backfill()
    library = tmp_path / "library"
    repo = ItemRepository(library)
    created = repo.create_item(
        ItemCreate(
            title="Thread prompt",
            source_name="X / Twitter",
            source_url="https://x.com/example/status/301",
            author="@example",
            notes="Original X status: https://x.com/example/status/301\n\nOriginal tweet intro:\nMain post intro\nPrompt below 👇",
            tags=["X source", "x-status-301"],
            prompts=[PromptIn(language="en", text="Main post intro\nPrompt below 👇", is_primary=True)],
        ),
        imported=True,
    )

    monkeypatch.setattr(
        backfill.GALLERY,
        "_manifest_for",
        lambda url, output_dir, dry_run=True, prompt_override=None, title_override=None: (
            output_dir / "dummy.json",
            {
                "prompt_text": "Create a premium brand poster.\nDesign requirements: matte paper, oversized headline, centered bottle.",
                "prompt_language": "en",
                "tweet_intro": "Main post intro\nPrompt below 👇",
                "prompt_reply_url": "https://x.com/example/status/302",
            },
        ),
    )
    monkeypatch.setattr(backfill.subprocess, "run", lambda *args, **kwargs: None)

    result = backfill.run_backfill(library_path=library)

    assert result["updated"] == 1
    detail = repo.get_item(created.id)
    assert detail.prompts[0].text.startswith("Create a premium brand poster.")
    assert "Prompt reply: https://x.com/example/status/302" in (detail.notes or "")
