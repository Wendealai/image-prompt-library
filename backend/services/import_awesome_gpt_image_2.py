from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image
from backend.services.import_sample_bundle import _already_imported, _clean_text, _replace_prompts_exactly
from backend.services.text_normalize import to_traditional

SOURCE_NAME = "freestylefly/awesome-gpt-image-2"
SOURCE_LICENSE = "MIT"
SOURCE_REPO_URL = "https://github.com/freestylefly/awesome-gpt-image-2"
SOURCE_BLOB_BASE = f"{SOURCE_REPO_URL}/blob/main"
SOURCE_RAW_BASE = "https://raw.githubusercontent.com/freestylefly/awesome-gpt-image-2/main"
DEFAULT_GALLERY_FILENAME = "gallery-part-2.md"
DEFAULT_GALLERY_PATH = Path("docs") / "gallery-part-2.md"

CASE_HEADING_RE = re.compile(r"^###\s+例\s+(?P<number>\d+)[：:]\s*(?P<title>.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[(?P<alt>(?:\\.|[^\]])*)\]\((?P<path>[^)]+)\)", re.DOTALL)
SOURCE_LINE_RE = re.compile(r"^\*\*来源：\*\*\s*(?P<source>.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)")
FENCE_RE = re.compile(r"```(?:text|json)?\s*\n(?P<text>.*?)\n```", re.DOTALL)

COLLECTIONS = [
    {"id": "ui-interface", "name": "UI与界面"},
    {"id": "infographic-visualization", "name": "图表与信息可视化"},
    {"id": "poster-typography", "name": "海报与排版"},
    {"id": "product-ecommerce", "name": "商品与电商"},
    {"id": "brand-logo", "name": "品牌与标志"},
    {"id": "photography-realism", "name": "摄影与写实"},
    {"id": "illustration-art", "name": "插画与艺术"},
    {"id": "characters", "name": "人物与角色"},
    {"id": "scene-narrative", "name": "场景与叙事"},
    {"id": "historical-classical", "name": "历史与古风题材"},
]
COLLECTION_LOOKUP = {collection["id"]: collection for collection in COLLECTIONS}

# Explicit curation for the requested import range. The titles are intentionally
# mapped by case number so repeated imports do not drift when prompt wording changes.
CURATED_COLLECTION_BY_CASE = {
    310: "infographic-visualization",
    311: "photography-realism",
    312: "product-ecommerce",
    313: "product-ecommerce",
    314: "photography-realism",
    315: "scene-narrative",
    316: "characters",
    317: "photography-realism",
    318: "photography-realism",
    319: "photography-realism",
    320: "poster-typography",
    321: "photography-realism",
    322: "photography-realism",
    323: "ui-interface",
    324: "scene-narrative",
    325: "characters",
    326: "photography-realism",
    327: "product-ecommerce",
    328: "photography-realism",
    329: "characters",
    330: "ui-interface",
    331: "infographic-visualization",
    332: "product-ecommerce",
    333: "infographic-visualization",
    334: "infographic-visualization",
    335: "ui-interface",
    336: "ui-interface",
    337: "historical-classical",
    338: "historical-classical",
    339: "infographic-visualization",
    340: "photography-realism",
    341: "infographic-visualization",
    342: "product-ecommerce",
    343: "poster-typography",
    344: "poster-typography",
    345: "poster-typography",
    346: "illustration-art",
    347: "infographic-visualization",
    348: "infographic-visualization",
    349: "poster-typography",
    350: "infographic-visualization",
    351: "brand-logo",
    352: "historical-classical",
    353: "infographic-visualization",
    354: "brand-logo",
    355: "poster-typography",
    356: "poster-typography",
    357: "photography-realism",
    358: "product-ecommerce",
    359: "illustration-art",
    360: "infographic-visualization",
    361: "infographic-visualization",
}


def _case_slug(number: int) -> str:
    return f"awesome-gpt-image-2-case-{number}"


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    return normalized.lstrip("./")


def _unescape_markdown(value: str) -> str:
    return value.replace("\\_", "_").strip()


def _gallery_path(source: Path | str, gallery_path: Path | str | None = None) -> Path:
    path = Path(source)
    if path.is_file():
        return path

    candidates: list[Path] = []
    if gallery_path is not None:
        requested = Path(gallery_path)
        candidates.append(path / requested)
        if len(requested.parts) == 1:
            candidates.append(path / "docs" / requested)
    else:
        candidates.extend((path / DEFAULT_GALLERY_PATH, path / DEFAULT_GALLERY_FILENAME))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    expected = " or ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Expected {expected}")


def _repo_root_for_gallery(gallery_path: Path) -> Path:
    if gallery_path.parent.name == "docs":
        return gallery_path.parent.parent
    return gallery_path.parent


def _repo_relative_gallery_path(gallery_path: Path, root: Path) -> str:
    try:
        return gallery_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return gallery_path.name


def _gallery_part_tag(gallery_repo_path: str) -> str:
    match = re.search(r"gallery-part-(?P<number>\d+)", gallery_repo_path)
    if match:
        return f"awesome_gpt_image_2_part_{match.group('number')}"
    safe = re.sub(r"[^a-z0-9]+", "_", Path(gallery_repo_path).stem.lower()).strip("_")
    return f"awesome_gpt_image_2_{safe}" if safe else "awesome_gpt_image_2_gallery"


def _markdown_sections(text: str) -> list[tuple[int, str, str]]:
    matches = list(CASE_HEADING_RE.finditer(text))
    sections: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((int(match.group("number")), match.group("title").strip(), text[match.end():end]))
    return sections


def _source_links(body: str) -> list[dict[str, str]]:
    source_match = SOURCE_LINE_RE.search(body)
    if not source_match:
        return []
    links = []
    for match in LINK_RE.finditer(source_match.group("source")):
        links.append({"label": _unescape_markdown(match.group("label")), "url": match.group("url").strip()})
    return links


def _split_bilingual_prompt(text: str) -> list[PromptIn]:
    prompt = text.strip()
    zh_marker = "[中文]"
    en_marker = "[English]"
    prompts: list[PromptIn] = []
    if zh_marker in prompt and en_marker in prompt:
        zh_start = prompt.index(zh_marker) + len(zh_marker)
        en_start = prompt.index(en_marker)
        zh_text = prompt[zh_start:en_start].strip()
        en_text = prompt[en_start + len(en_marker):].strip()
        if en_text:
            prompts.append(PromptIn(language="en", text=en_text, is_primary=True))
        if zh_text:
            prompts.append(PromptIn(language="zh_hant", text=to_traditional(zh_text), is_primary=not bool(prompts)))
            prompts.append(PromptIn(language="zh_hans", text=zh_text, is_primary=False))
        return prompts

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", prompt))
    latin_count = len(re.findall(r"[A-Za-z]", prompt))
    if cjk_count > max(12, latin_count // 3):
        prompts.append(PromptIn(language="zh_hant", text=to_traditional(prompt), is_primary=True))
        prompts.append(PromptIn(language="zh_hans", text=prompt, is_primary=False))
    elif prompt:
        prompts.append(PromptIn(language="en", text=prompt, is_primary=True))
    return prompts


def _fallback_collection_id(record: dict[str, Any]) -> str:
    text = f"{record.get('title', '')}\n{record.get('prompt_text', '')}".lower()
    if re.search(r"\bui\b", text) or any(token in text for token in ["界面", "网页", "应用", "截图", "朋友圈", "直播"]):
        return "ui-interface"
    if any(token in text for token in ["信息图", "图表", "详解", "拆解", "分析", "数据", "地图", "infographic"]):
        return "infographic-visualization"
    if any(token in text for token in ["logo", "品牌身份", "标志"]):
        return "brand-logo"
    if any(token in text for token in ["商品", "产品", "电商", "广告", "包装", "饮料", "口红"]):
        return "product-ecommerce"
    if any(token in text for token in ["海报", "排版", "字体", "封面", "poster", "campaign"]):
        return "poster-typography"
    if any(token in text for token in ["古风", "诗词", "西楚", "赤壁", "短歌行"]):
        return "historical-classical"
    if any(token in text for token in ["插画", "水墨", "刺绣", "illustration"]):
        return "illustration-art"
    if any(token in text for token in ["角色", "少年", "少女", "漫画", "皮克斯"]):
        return "characters"
    if any(token in text for token in ["人像", "写真", "摄影", "portrait", "photo"]):
        return "photography-realism"
    return "scene-narrative"


def _collection_id_for_record(record: dict[str, Any]) -> str:
    number = int(record["number"])
    return CURATED_COLLECTION_BY_CASE.get(number) or _fallback_collection_id(record)


def _notes(record: dict[str, Any]) -> str:
    parts = [
        f"Imported from {SOURCE_NAME} {record['gallery_label']} cases for demo/reference use.",
        f"License observed in upstream repository: {SOURCE_LICENSE}. Preserve upstream and original-source attribution when publishing screenshots, demo GIFs, or fixtures.",
        f"Original case: {record['case_url']}",
    ]
    source_links = record.get("source_links") or []
    if source_links:
        parts.append("Original linked source(s): " + "; ".join(f"{link['label']} {link['url']}" for link in source_links))
    raw_image_url = _clean_text(record.get("raw_image_url"))
    if raw_image_url:
        parts.append(f"Original image URL: {raw_image_url}")
    return "\n".join(parts)


def load_gallery_cases(
    source: Path | str,
    start_case: int = 310,
    end_case: int | None = None,
    gallery_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    gallery = _gallery_path(source, gallery_path=gallery_path).resolve()
    root = _repo_root_for_gallery(gallery)
    gallery_repo_path = _repo_relative_gallery_path(gallery, root)
    gallery_label = Path(gallery_repo_path).stem
    part_tag = _gallery_part_tag(gallery_repo_path)
    text = gallery.read_text(encoding="utf-8")
    records: list[dict[str, Any]] = []
    for number, title, body in _markdown_sections(text):
        if number < start_case or (end_case is not None and number > end_case):
            continue
        image_match = IMAGE_RE.search(body)
        prompt_match = FENCE_RE.search(body)
        if not image_match or not prompt_match:
            continue
        image_path = _normalize_repo_path(image_match.group("path"))
        if image_path.startswith("../"):
            image_path = image_path[3:]
        image_path = image_path.replace("\\", "/").lstrip("/")
        source_links = _source_links(body)
        prompt_text = prompt_match.group("text").strip()
        collection_id = _collection_id_for_record({"number": number, "title": title, "prompt_text": prompt_text})
        records.append(
            {
                "id": f"case-{number}",
                "number": number,
                "title": title,
                "image_alt": image_match.group("alt").strip() or title,
                "image": image_path,
                "local_image_path": (root / image_path).resolve(),
                "raw_image_url": f"{SOURCE_RAW_BASE}/{image_path}",
                "source_links": source_links,
                "author": " / ".join(link["label"] for link in source_links) or SOURCE_NAME,
                "case_url": f"{SOURCE_BLOB_BASE}/{gallery_repo_path}#case-{number}",
                "source_url": f"{SOURCE_BLOB_BASE}/{gallery_repo_path}#case-{number}",
                "gallery_path": gallery_repo_path,
                "gallery_label": gallery_label,
                "part_tag": part_tag,
                "prompt_text": prompt_text,
                "prompts": _split_bilingual_prompt(prompt_text),
                "collection_id": collection_id,
                "collection_name": COLLECTION_LOOKUP[collection_id]["name"],
            }
        )
    return sorted(records, key=lambda record: int(record["number"]))


def _image_bytes(record: dict[str, Any]) -> tuple[bytes, str]:
    local_image_path = record.get("local_image_path")
    if isinstance(local_image_path, Path) and local_image_path.is_file():
        return local_image_path.read_bytes(), local_image_path.name
    raw_image_url = str(record["raw_image_url"])
    with urlopen(raw_image_url) as response:
        return response.read(), Path(raw_image_url).name


def import_awesome_gpt_image_2(
    source: Path | str,
    library: Path | str,
    start_case: int = 310,
    end_case: int | None = None,
    gallery_path: Path | str | None = None,
) -> ImportResult:
    library_path = Path(library)
    init_db(library_path)
    repo = ItemRepository(library_path)
    batch_id = new_id("imp")
    started = now()
    item_count = 0
    image_count = 0
    log: list[str] = []

    with connect(library_path) as conn:
        conn.execute(
            "INSERT INTO imports(id,source_name,source_path,status,started_at,log) VALUES(?,?,?,?,?,?)",
            (batch_id, SOURCE_NAME, str(source), "running", started, ""),
        )
        conn.commit()

    for record in load_gallery_cases(source, start_case=start_case, end_case=end_case, gallery_path=gallery_path):
        slug = _case_slug(int(record["number"]))
        if _already_imported(library_path, slug):
            continue
        prompts = record["prompts"]
        if not prompts:
            log.append(f"Skipping case {record['number']}: missing prompt")
            continue
        tags = [
            "sample",
            "awesome_gpt_image_2",
            record["part_tag"],
            record["collection_id"],
        ]
        created = repo.create_item(
            ItemCreate(
                title=record["title"],
                slug=slug,
                model="GPT Image 2 sample",
                cluster_name=record["collection_name"],
                tags=tags,
                prompts=prompts,
                source_name=SOURCE_NAME,
                source_url=record["case_url"],
                author=record["author"],
                notes=_notes(record),
            ),
            imported=True,
        )
        _replace_prompts_exactly(library_path, repo, created.id, prompts)
        item_count += 1
        try:
            data, filename = _image_bytes(record)
        except Exception as exc:
            log.append(f"Missing image for {slug}: {record['image']} ({exc})")
            continue
        stored = store_image(library_path, data, filename)
        repo.add_image(
            created.id,
            StoredImageInput(
                stored.original_path,
                stored.thumb_path,
                stored.preview_path,
                width=stored.width,
                height=stored.height,
                file_sha256=stored.file_sha256,
                role="result_image",
            ),
        )
        image_count += 1

    with connect(library_path) as conn:
        conn.execute(
            "UPDATE imports SET status=?, item_count=?, image_count=?, finished_at=?, log=? WHERE id=?",
            ("completed", item_count, image_count, now(), "\n".join(log), batch_id),
        )
        conn.commit()
    return ImportResult(id=batch_id, item_count=item_count, image_count=image_count, status="completed", log="\n".join(log))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import freestylefly/awesome-gpt-image-2 gallery cases into Image Prompt Library.")
    parser.add_argument("--source", required=True, help="Path to a local clone/root or gallery markdown file")
    parser.add_argument("--library", default="library", help="Image Prompt Library data path")
    parser.add_argument("--start-case", type=int, default=310, help="First case number to import")
    parser.add_argument("--end-case", type=int, default=None, help="Optional final case number to import")
    parser.add_argument("--gallery-path", default=None, help="Gallery path inside the source root, e.g. docs/gallery-part-1.md")
    args = parser.parse_args()
    print(
        import_awesome_gpt_image_2(
            args.source,
            args.library,
            start_case=args.start_case,
            end_case=args.end_case,
            gallery_path=args.gallery_path,
        ).model_dump_json(indent=2)
    )


if __name__ == "__main__":
    main()
