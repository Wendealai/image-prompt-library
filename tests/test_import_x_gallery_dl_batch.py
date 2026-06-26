from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_batch():
    path = ROOT / "scripts" / "import-x-gallery-dl-batch.py"
    spec = importlib.util.spec_from_file_location("import_x_gallery_dl_batch_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prompt_payload_prefers_thread_reply_when_main_post_says_prompt_below(monkeypatch):
    batch = load_batch()
    source_url = "https://x.com/example/status/101"
    meta = {
        "tweet_id": "101",
        "content": "Poster preview\nPrompt below 👇",
        "author": {"name": "example"},
    }

    monkeypatch.setattr(
        batch,
        "_nitter_thread_tweets",
        lambda status: [
            {"href": source_url, "content": "Poster preview\nPrompt below 👇"},
            {"href": "https://x.com/example/status/102", "content": "Create a clean editorial poster.\nDesign requirements: white background, red accent."},
        ],
    )

    prompt, reply_url = batch._prompt_payload(meta, [], source_url)

    assert prompt.startswith("Create a clean editorial poster.")
    assert reply_url == "https://x.com/example/status/102"


def test_prompt_payload_keeps_main_post_when_it_already_contains_full_prompt(monkeypatch):
    batch = load_batch()
    source_url = "https://x.com/example/status/201"
    content = "Prompt: Create a minimalist poster with brutalist typography and a cream paper texture."
    meta = {
        "tweet_id": "201",
        "content": content,
        "author": {"name": "example"},
    }

    monkeypatch.setattr(batch, "_nitter_thread_tweets", lambda status: [])

    prompt, reply_url = batch._prompt_payload(meta, [], source_url)

    assert prompt == "Create a minimalist poster with brutalist typography and a cream paper texture."
    assert reply_url is None
