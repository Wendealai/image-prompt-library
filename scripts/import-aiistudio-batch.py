#!/usr/bin/env python3
"""Import public aiiStudio prompt pages into the local prompt library."""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "aiistudio-imports"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "section", "article", "header", "footer", "li", "pre", "code", "h1", "h2", "h3", "button"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "section", "article", "header", "footer", "li", "pre", "code", "h1", "h2", "h3", "button"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [line.strip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def _load_importer():
    path = ROOT / "scripts" / "import-x-prompt.py"
    spec = importlib.util.spec_from_file_location("import_prompt_for_aiistudio", path)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def _fetch_text(url: str) -> str:
    return _fetch_bytes(url).decode("utf-8", "replace")


def _page_id(url: str) -> str:
    match = re.search(r"/prompt/(\d+)", url)
    if not match:
        raise ValueError(f"Could not infer aiiStudio prompt id from {url}")
    return match.group(1)


def _slug(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    slug = path.rsplit("/", 1)[-1] if "/" in path else path
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-") or _page_id(url)


def _title(html_text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    if not match:
        return "aiiStudio Prompt"
    title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    title = re.sub(r"\s*:\s*GPT Image 2 prompt\s*$", "", title, flags=re.I).strip()
    return f"{title} Prompt" if not title.lower().endswith("prompt") else title


def _body_text(html_text: str) -> str:
    parser = TextExtractor()
    parser.feed(html_text)
    return parser.text()


def _prompt_text(body_text: str) -> str:
    marker = "\nCopy Prompt\n"
    start = body_text.find(marker)
    if start < 0:
        raise ValueError("Could not locate Copy Prompt marker.")
    after = body_text[start + len(marker) :]
    end = after.find("\nGenerate Free Now\n")
    if end < 0:
        end = after.find("\nUse as Reference\n")
    prompt = after[:end if end >= 0 else None].strip()
    lines = [line for line in prompt.splitlines() if line.strip() not in {"|", "esc"}]
    prompt = "\n".join(lines).strip()
    prompt = re.sub(r"^(?:\|\s*)?esc\s*", "", prompt).strip()
    if not prompt:
        raise ValueError("Extracted prompt text is empty.")
    return prompt


def _author(body_text: str) -> str | None:
    match = re.search(r"\n([^\n]{2,80})\n(@[A-Za-z0-9_]{2,32})\nCopy Prompt\n", body_text)
    if match:
        name, handle = (part.strip() for part in match.groups())
        return f"{name} ({handle})"
    match = re.search(r"\n(@[A-Za-z0-9_]{2,32})\nCopy Prompt\n", body_text)
    return match.group(1) if match else None


def _image_urls(html_text: str, prompt_id: str) -> list[str]:
    urls = re.findall(
        rf"https://cdn[.]aiistudio[.]com/(?:cdn-cgi/image/[^\"'<>\s]+/)?[A-Za-z0-9_-]+/{re.escape(prompt_id)}/\d+[.]jpg",
        html.unescape(html_text),
    )
    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        url = re.sub(r"https://cdn[.]aiistudio[.]com/cdn-cgi/image/[^/]+/", "https://cdn.aiistudio.com/", url)
        if url not in seen:
            seen.add(url)
            normalized.append(url)
    return normalized


def _download_images(urls: list[str], image_dir: Path) -> list[dict[str, str]]:
    image_dir.mkdir(parents=True, exist_ok=True)
    images: list[dict[str, str]] = []
    for index, url in enumerate(urls):
        filename = f"{index}.jpg"
        path = image_dir / filename
        path.write_bytes(_fetch_bytes(url))
        images.append({"path": str(path), "filename": filename, "role": "result_image"})
    return images


def build_manifest(url: str, output_dir: Path) -> Path:
    prompt_id = _page_id(url)
    html_text = _fetch_text(url)
    body = _body_text(html_text)
    item_dir = output_dir / prompt_id
    item_dir.mkdir(parents=True, exist_ok=True)
    images = _download_images(_image_urls(html_text, prompt_id), item_dir / "images")
    if not images:
        raise ValueError(f"No aiiStudio images found for {url}")
    manifest = {
        "source_url": url.split("?", 1)[0],
        "source_name": "aiiStudio",
        "title": _title(html_text),
        "author": _author(body),
        "model": "ChatGPT Image2",
        "prompt_language": "en",
        "prompt_text": _prompt_text(body),
        "tags": ["aiiStudio", "GPT Image 2", f"aiistudio-{prompt_id}"],
        "image_filename_prefix": f"aiistudio-{prompt_id}-{_slug(url)}",
        "notes": "Imported from public aiiStudio prompt page.",
        "images": images,
    }
    manifest = {key: value for key, value in manifest.items() if value not in (None, "", [])}
    manifest_path = item_dir / f"aiistudio-{prompt_id}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--url-file")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--library", default=str(ROOT / "library"))
    parser.add_argument("--after-import", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    urls = list(args.urls)
    if args.url_file:
        urls.extend(
            line.strip()
            for line in Path(args.url_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not urls:
        raise SystemExit("No aiiStudio URLs supplied.")

    importer = _load_importer()
    output_dir = args.output_dir.resolve()
    library_path = Path(args.library).resolve()
    results: list[dict[str, Any]] = []
    created = False
    for url in urls:
        manifest_path = build_manifest(url, output_dir)
        if args.dry_run:
            results.append({"url": url, "manifest": str(manifest_path), "status": "dry-run"})
            continue
        result = importer.import_manifest(manifest_path, library_path)
        created = created or result.get("status") == "created"
        results.append({"url": url, "manifest": str(manifest_path), **result})

    if args.after_import and created:
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
