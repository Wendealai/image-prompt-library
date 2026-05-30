#!/usr/bin/env python3
"""Build an import-x-prompt manifest from browser-captured X/Nitter JSON."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object.")
    return data


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def _x_url_from_any(value: str | None) -> str | None:
    if not value:
        return None
    if "x.com/" in value:
        return value.split("?", 1)[0].replace("#m", "")
    parsed = urlparse(value)
    match = re.search(r"/([^/]+)/status/(\d+)", parsed.path)
    if match:
        user, status_id = match.groups()
        return f"https://x.com/{user}/status/{status_id}"
    return None


def _status_id(source_url: str) -> str | None:
    match = re.search(r"/status/(\d+)", source_url)
    return match.group(1) if match else None


def _author_from_source(source_url: str) -> str | None:
    match = re.search(r"x\.com/([^/]+)/status/", source_url)
    return f"@{match.group(1)}" if match else None


def _author_from_title(title: str | None) -> str | None:
    match = re.search(r"\(@([^)]+)\)", title or "")
    return f"@{match.group(1)}" if match else None


def _tweet_href(tweet: dict[str, Any]) -> str | None:
    href = tweet.get("href")
    if isinstance(href, str):
        return _x_url_from_any(href)
    return None


def _tweet_content(tweet: dict[str, Any]) -> str:
    return _clean_text(tweet.get("content") or tweet.get("text"))


def _tweets(thread: dict[str, Any]) -> list[dict[str, Any]]:
    tweets = thread.get("tweets")
    if isinstance(tweets, list):
        return [tweet for tweet in tweets if isinstance(tweet, dict)]
    return []


def _main_tweet(tweets: list[dict[str, Any]], source_url: str) -> dict[str, Any] | None:
    source_status = _status_id(source_url)
    if source_status:
        for tweet in tweets:
            href = _tweet_href(tweet) or ""
            if f"/status/{source_status}" in href and _tweet_content(tweet):
                return tweet
    for tweet in tweets:
        if _tweet_content(tweet):
            return tweet
    return None


def _prompt_score(tweet: dict[str, Any], source_url: str, author: str | None) -> int:
    content = _tweet_content(tweet)
    if not content:
        return -1000
    href = _tweet_href(tweet) or ""
    source_status = _status_id(source_url)
    score = len(content)
    if source_status and f"/status/{source_status}" in href:
        score -= 5000
    if "提示词" in content or "prompt" in content.lower():
        score += 1000
    if any(marker in content for marker in ("画面要求", "设计要求", "请生成", "生成一张")):
        score += 600
    if author and author.lstrip("@").lower() in href.lower():
        score += 300
    return score


def _prompt_tweet(tweets: list[dict[str, Any]], source_url: str, author: str | None, explicit_url: str | None) -> dict[str, Any] | None:
    if explicit_url:
        explicit_status = _status_id(explicit_url)
        for tweet in tweets:
            href = _tweet_href(tweet) or ""
            if explicit_status and f"/status/{explicit_status}" in href:
                return tweet
    candidates = [tweet for tweet in tweets if _tweet_content(tweet)]
    if not candidates:
        return None
    return max(candidates, key=lambda tweet: _prompt_score(tweet, source_url, author))


def _image_entries(images_json: dict[str, Any]) -> list[dict[str, str]]:
    raw_images = images_json.get("images")
    if not isinstance(raw_images, list) or not raw_images:
        raise SystemExit("Image JSON must contain an `images` array.")
    entries: list[dict[str, str]] = []
    for index, image in enumerate(raw_images, start=1):
        if not isinstance(image, dict):
            continue
        entry: dict[str, str] = {}
        if isinstance(image.get("dataUrl"), str):
            entry["data_url"] = image["dataUrl"]
        elif isinstance(image.get("data_url"), str):
            entry["data_url"] = image["data_url"]
        elif isinstance(image.get("base64"), str):
            entry["base64"] = image["base64"]
        elif isinstance(image.get("path"), str):
            entry["path"] = image["path"]
        else:
            continue
        if isinstance(image.get("contentType"), str):
            entry["content_type"] = image["contentType"]
        elif isinstance(image.get("content_type"), str):
            entry["content_type"] = image["content_type"]
        filename = image.get("filename")
        if isinstance(filename, str) and filename.strip():
            entry["filename"] = filename.strip()
        elif isinstance(image.get("path"), str):
            entry["filename"] = Path(image["path"]).name
        else:
            entry["filename"] = f"image-{index}.jpg"
        entries.append(entry)
    if not entries:
        raise SystemExit("No importable images found in image JSON.")
    return entries


def _default_title(source_url: str, prompt_text: str) -> str:
    status = _status_id(source_url) or "x"
    first_line = next((line.strip(" ：:") for line in prompt_text.splitlines() if line.strip()), "")
    if first_line:
        first_line = re.sub(r"[《》「」]", "", first_line)
        if len(first_line) > 32:
            first_line = first_line[:32].rstrip()
        return f"{first_line} Prompt"
    return f"X Prompt {status}"


def build_manifest(
    *,
    thread_json: Path,
    images_json: Path,
    output: Path,
    source_url: str | None = None,
    title: str | None = None,
    author: str | None = None,
    prompt_reply_url: str | None = None,
    cluster_name: str | None = None,
    tags: list[str] | None = None,
    model: str = "ChatGPT Image2",
    prompt_language: str = "zh_hans",
) -> dict[str, Any]:
    thread = _load_json(thread_json)
    images = _load_json(images_json)
    resolved_source = _x_url_from_any(source_url) or _x_url_from_any(thread.get("url")) or _x_url_from_any(thread.get("title"))
    if not resolved_source:
        raise SystemExit("Could not infer source_url. Pass --source-url.")
    resolved_author = author or _author_from_title(thread.get("title")) or _author_from_source(resolved_source)
    tweets = _tweets(thread)
    main = _main_tweet(tweets, resolved_source)
    prompt = _prompt_tweet(tweets, resolved_source, resolved_author, prompt_reply_url)
    prompt_text = _tweet_content(prompt or {}) or _clean_text(thread.get("prompt_text"))
    if not prompt_text:
        raise SystemExit("Could not infer prompt_text. Add a prompt tweet to thread JSON or edit the manifest manually.")
    prompt_url = _x_url_from_any(prompt_reply_url) or _tweet_href(prompt or {})
    status = _status_id(resolved_source)
    final_tags = ["X source"]
    if status:
        final_tags.append(f"x-status-{status}")
    final_tags.append("GPT Image 2")
    for tag in tags or []:
        clean = tag.strip()
        if clean and clean not in final_tags:
            final_tags.append(clean)

    manifest: dict[str, Any] = {
        "source_url": resolved_source,
        "title": title or _default_title(resolved_source, prompt_text),
        "author": resolved_author,
        "model": model,
        "prompt_language": prompt_language,
        "prompt_text": prompt_text,
        "tweet_intro": _tweet_content(main or {}),
        "cluster_name": cluster_name,
        "tags": final_tags,
        "image_filename_prefix": f"{(resolved_author or 'x').lstrip('@').lower()}-{status or 'prompt'}",
        "images": _image_entries(images),
    }
    if prompt_url and prompt_url != resolved_source:
        manifest["prompt_reply_url"] = prompt_url
    manifest = {key: value for key, value in manifest.items() if value not in (None, "", [])}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-json", type=Path, required=True)
    parser.add_argument("--images-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--prompt-reply-url")
    parser.add_argument("--cluster-name")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--model", default="ChatGPT Image2")
    parser.add_argument("--prompt-language", default="zh_hans")
    args = parser.parse_args()

    manifest = build_manifest(
        thread_json=args.thread_json,
        images_json=args.images_json,
        output=args.output,
        source_url=args.source_url,
        title=args.title,
        author=args.author,
        prompt_reply_url=args.prompt_reply_url,
        cluster_name=args.cluster_name,
        tags=args.tag,
        model=args.model,
        prompt_language=args.prompt_language,
    )
    print(f"Wrote {args.output}")
    print(json.dumps({key: manifest.get(key) for key in ("source_url", "title", "author", "prompt_reply_url")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
