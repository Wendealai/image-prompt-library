#!/usr/bin/env python3
"""Import public X/Twitter prompt posts from gallery-dl JSON metadata."""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "x-gallery-dl-imports"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load_importer():
    path = ROOT / "scripts" / "import-x-prompt.py"
    spec = importlib.util.spec_from_file_location("import_x_prompt_for_gallery_dl", path)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status_id(url: str) -> str | None:
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _points_to_replies(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in text
        for marker in (
            "评论区",
            "见评论",
            "在评论",
            "评论见",
            "下方评论",
            "评论区见",
            "见评论区",
            "提示词见评论区",
            "提示词放评论区",
            "评论区补充",
        )
    ) or any(
        marker in lowered
        for marker in (
            "in comments",
            "in comment",
            "comment section",
            "comments below",
            "prompt below",
            "prompt in comments",
            "prompt in comment",
            "see comments",
            "check comments",
        )
    )


def _nitter_cookie(html_text: str) -> str | None:
    match = re.search(r"['\"]([0-9A-F]{40})['\"]", html_text)
    if not match:
        return None
    seed = match.group(1)
    index = int(seed[0], 16)
    suffix = 0
    while True:
        digest = hashlib.sha1((seed + str(suffix)).encode()).digest()
        if digest[index] == 0xB0 and digest[index + 1] == 0x0B:
            return "res=" + seed + str(suffix)
        suffix += 1


def _fetch_text(url: str, cookie: str | None = None) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    if cookie:
        headers["Cookie"] = cookie
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _nitter_thread_texts(status: str) -> list[str]:
    return [tweet["content"] for tweet in _nitter_thread_tweets(status)]


def _nitter_thread_tweets(status: str) -> list[dict[str, str]]:
    url = f"https://nitter.poast.org/i/status/{status}"
    try:
        html_text = _fetch_text(url)
    except Exception as exc:
        html_text = getattr(exc, "read", lambda: b"")().decode("utf-8", "replace")
    cookie = _nitter_cookie(html_text)
    if cookie:
        html_text = _fetch_text(url, cookie)
    tweets: list[dict[str, str]] = []
    pattern = re.compile(
        r'<div class="timeline-item[\s\S]*?<a class="tweet-link" href="([^"]+)"[\s\S]*?<div class="tweet-content media-body"[^>]*>(.*?)</div>',
        re.S,
    )
    for href, raw in pattern.findall(html_text):
        text = re.sub(r"<br\s*/?>", "\n", raw)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text).strip()
        if text:
            tweets.append(
                {
                    "href": href if href.startswith("http") else f"https://x.com{href.split('#', 1)[0]}",
                    "content": _clean_text(text),
                }
            )
    return tweets


def _tweet_content(tweet: dict[str, str]) -> str:
    return _clean_text(tweet.get("content"))


def _tweet_href(tweet: dict[str, str]) -> str:
    return str(tweet.get("href") or "")


def _looks_like_prompt_text(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    explicit_markers = (
        "prompt:",
        "prompt：",
        "提示词:",
        "提示词：",
        "设计要求",
        "画面要求",
        "请生成",
        "生成一张",
    )
    if any(marker in lower for marker in explicit_markers):
        return True
    return ("prompt" in lower or "提示词" in content) and len(content) >= 120


def _prompt_score(tweet: dict[str, str], source_url: str, author: str | None) -> int:
    content = _tweet_content(tweet)
    if not content:
        return -1000
    href = _tweet_href(tweet)
    source_status = _status_id(source_url)
    score = len(content)
    looks_like_prompt = _looks_like_prompt_text(content)
    if source_status and f"/status/{source_status}" in href:
        score += 5000 if looks_like_prompt else -500
    if looks_like_prompt:
        score += 1000
    if author and author.lstrip("@").lower() in href.lower():
        score += 300
    return score


def _thread_prompt_candidate(status: str, source_url: str, author: str | None) -> tuple[str, str | None]:
    tweets = _nitter_thread_tweets(status)
    if not tweets:
        return "", None
    main_href = source_url.split("?", 1)[0]
    main_tweet = next((tweet for tweet in tweets if _tweet_href(tweet) == main_href), tweets[0])
    if _looks_like_prompt_text(_tweet_content(main_tweet)):
        return _tweet_content(main_tweet), None
    candidate = max(tweets, key=lambda tweet: _prompt_score(tweet, source_url, author))
    prompt_text = _tweet_content(candidate)
    if not prompt_text:
        return "", None
    reply_url = _tweet_href(candidate)
    if reply_url == main_href:
        reply_url = None
    return prompt_text, reply_url


def _reply_prompt(status: str, main_content: str) -> str:
    if not status or not _points_to_replies(main_content):
        return ""
    candidates = _nitter_thread_texts(status)[1:]
    candidates = [text for text in candidates if text and not _points_to_replies(text)]
    if not candidates:
        return ""
    return max(candidates, key=len)


def _prompt_payload(meta: dict[str, Any], media: list[dict[str, Any]], source_url: str) -> tuple[str, str | None]:
    content = _clean_text(meta.get("content"))
    status = str(meta.get("tweet_id") or _status_id(source_url) or "").strip()
    author_data = meta.get("author") if isinstance(meta.get("author"), dict) else meta.get("user")
    handle = author_data.get("name") if isinstance(author_data, dict) else None
    author = f"@{handle.lstrip('@')}" if isinstance(handle, str) and handle else None
    reply_prompt = _reply_prompt(status, content)
    if reply_prompt:
        thread_prompt, reply_url = _thread_prompt_candidate(status, source_url, author)
        if thread_prompt:
            return thread_prompt, reply_url
        return reply_prompt, None
    match = re.search(r"(?:^|\n)\s*(?:💬\s*)?(?:prompt\s*[:：]|提示词(?:示例)?\s*[:：]?)(.+)$", content, re.I | re.S)
    if match:
        prompt = match.group(1).strip()
        prompt = re.split(
            r"\n\s*(?:check\s+alt|check\s+atl|alts?\b|参考|inspiration)\b",
            prompt,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        prompt = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", prompt).strip()
        prompt = re.sub(r"\s*```$", "", prompt).strip()
        if prompt:
            return prompt, None
    if status and (not content or _points_to_replies(content) or not _looks_like_prompt_text(content)):
        thread_prompt, reply_url = _thread_prompt_candidate(status, source_url, author)
        if thread_prompt and thread_prompt != content:
            return thread_prompt, reply_url
    if content:
        return content, None
    descriptions = [_clean_text(item.get("description")) for item in media]
    return max(descriptions, key=len, default=""), None


def _title(meta: dict[str, Any], prompt_text: str, status: str) -> str:
    content = _clean_text(meta.get("content"))
    share = re.search(r"prompt\s+share\s*[:：]\s*([^\n]+)", content, re.I)
    if share:
        raw = share.group(1).strip(" .:-")
    else:
        raw = next((line.strip(" ：:.") for line in content.splitlines() if line.strip()), "")
    if not raw:
        raw = next((line.strip(" ：:.") for line in prompt_text.splitlines() if line.strip()), "")
    raw = re.sub(r"[《》「」\"“”]", "", raw).strip()
    if len(raw) > 48:
        raw = raw[:48].rstrip()
    return f"{raw or f'X Prompt {status}'} Prompt"


def _source_url(input_url: str, meta: dict[str, Any]) -> str:
    status = str(meta.get("tweet_id") or _status_id(input_url) or "").strip()
    author = meta.get("author") if isinstance(meta.get("author"), dict) else meta.get("user")
    handle = author.get("name") if isinstance(author, dict) else None
    if status and isinstance(handle, str) and handle.strip():
        return f"https://x.com/{handle.strip().lstrip('@')}/status/{status}"
    if "x.com/" in input_url:
        return input_url.split("?", 1)[0]
    if status:
        return f"https://x.com/i/status/{status}"
    return input_url


def _language(meta: dict[str, Any]) -> str:
    lang = str(meta.get("lang") or "").lower()
    if lang.startswith("zh"):
        return "zh_hans"
    if lang.startswith("en"):
        return "en"
    return "zh_hans"


def _gallery_json(url: str) -> list[Any]:
    completed = subprocess.run(
        ["gallery-dl", "-j", url],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return json.loads(completed.stdout)


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def _prompt_override_from_item(item_id: str, library_path: Path) -> dict[str, str]:
    import sqlite3

    db_path = library_path / "db.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT p.language, p.text, c.name AS cluster_name
            FROM items i
            JOIN prompts p ON p.item_id = i.id
            LEFT JOIN clusters c ON c.id = i.cluster_id
            WHERE i.id = ?
            ORDER BY p.is_primary DESC, p.created_at ASC
            LIMIT 1
            """,
            (item_id,),
        ).fetchone()
    if not row:
        raise RuntimeError(f"Prompt source item not found: {item_id}")
    return {
        "prompt_language": row["language"],
        "prompt_text": row["text"],
        "cluster_name": row["cluster_name"] or "",
    }


def _manifest_for(
    url: str,
    output_dir: Path,
    *,
    dry_run: bool,
    prompt_override: dict[str, str] | None = None,
    title_override: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    raw = _gallery_json(url)
    tweet_meta: dict[str, Any] | None = None
    photos: list[tuple[str, dict[str, Any]]] = []
    for entry in raw:
        if not isinstance(entry, list) or not entry:
            continue
        if entry[0] == 2 and len(entry) > 1 and isinstance(entry[1], dict):
            tweet_meta = entry[1]
        if entry[0] == 3 and len(entry) > 2 and isinstance(entry[1], str) and isinstance(entry[2], dict):
            if entry[2].get("type") in (None, "photo"):
                photos.append((entry[1], entry[2]))
    if not tweet_meta and photos:
        tweet_meta = photos[0][1]
    if not tweet_meta:
        raise RuntimeError("No tweet metadata found.")
    if not photos:
        raise RuntimeError("No photo media found.")

    source_url = _source_url(url, tweet_meta)
    status = str(tweet_meta.get("tweet_id") or _status_id(source_url) or "x")
    author_data = tweet_meta.get("author") if isinstance(tweet_meta.get("author"), dict) else tweet_meta.get("user")
    handle = author_data.get("name") if isinstance(author_data, dict) else None
    author = f"@{handle.lstrip('@')}" if isinstance(handle, str) and handle else None
    media_meta = [item for _, item in photos]
    prompt, prompt_reply_url = (prompt_override.get("prompt_text"), None) if prompt_override else _prompt_payload(tweet_meta, media_meta, source_url)
    if not prompt:
        raise RuntimeError("No prompt text found.")

    item_dir = output_dir / status
    images: list[dict[str, str]] = []
    for index, (media_url, meta) in enumerate(photos, start=1):
        extension = str(meta.get("extension") or "jpg").lstrip(".")
        filename = f"{str(meta.get('filename') or f'{status}-{index}')}.{extension}"
        image_path = item_dir / "images" / filename
        if not dry_run and not image_path.exists():
            _download(media_url, image_path)
        images.append({"path": str(image_path), "filename": filename, "role": "result_image"})

    tags = ["X source", f"x-status-{status}", "GPT Image 2"]
    manifest = {
        "source_url": source_url,
        "title": title_override or _title(tweet_meta, prompt, status),
        "author": author,
        "model": "ChatGPT Image2",
        "prompt_language": (prompt_override or {}).get("prompt_language") or _language(tweet_meta),
        "prompt_text": prompt,
        "tweet_intro": _clean_text(tweet_meta.get("content")),
        "prompt_reply_url": prompt_reply_url,
        "cluster_name": (prompt_override or {}).get("cluster_name") or None,
        "tags": tags,
        "image_filename_prefix": f"{(handle or 'x').lstrip('@').lower()}-{status}",
        "images": images,
    }
    manifest = {key: value for key, value in manifest.items() if value not in (None, "", [])}
    manifest_path = item_dir / f"x-{status}.json"
    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path, manifest


def _urls_from_args(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    for path in args.url_file or []:
        urls.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [url for url in urls if url and not url.startswith("#")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--url-file", type=Path, action="append")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--library")
    parser.add_argument("--prompt-from-item-id", help="Reuse the primary prompt and collection from an existing item")
    parser.add_argument("--title", help="Override the imported item title")
    parser.add_argument("--after-import", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    urls = _urls_from_args(args)
    if not urls:
        raise SystemExit("Pass one or more X URLs.")

    importer = _load_importer()
    library_path = importer._library_path(args.library)
    prompt_override = _prompt_override_from_item(args.prompt_from_item_id, library_path) if args.prompt_from_item_id else None
    results: list[dict[str, Any]] = []
    created = 0
    for url in urls:
        try:
            manifest_path, manifest = _manifest_for(
                url,
                args.output_dir.resolve(),
                dry_run=args.dry_run,
                prompt_override=prompt_override,
                title_override=args.title,
            )
            result: dict[str, Any] = {
                "url": url,
                "manifest": str(manifest_path),
                "title": manifest["title"],
                "images": len(manifest["images"]),
                "prompt_language": manifest.get("prompt_language"),
                "prompt_preview": manifest["prompt_text"][:180].replace("\n", " "),
            }
            if not args.dry_run:
                import_result = importer.import_manifest(manifest_path.resolve(), library_path)
                result.update(import_result)
                if import_result["status"] == "created":
                    created += 1
            results.append(result)
        except Exception as exc:
            results.append({"url": url, "status": "error", "error": str(exc)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.after_import and created:
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    if any(item.get("status") == "error" for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
