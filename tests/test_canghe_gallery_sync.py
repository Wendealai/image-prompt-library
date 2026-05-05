from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.db import connect
from backend.main import create_app
from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, PromptIn
from backend.services.canghe_gallery_sync import (
    case_dedupe_keys,
    collect_existing_dedupe_keys,
    image_url_for_case,
    item_payload_for_case,
    prompt_hash,
    select_new_cases,
    sync_canghe_gallery,
)

ADMIN_PASSWORD = "zwyy0323"


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (18, 12), (30, 120, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


def _case(**overrides):
    payload = {
        "id": 385,
        "title": "Qingdao Beer Fashion Set",
        "image": "/images/case385.jpg",
        "sourceLabel": "@Popcraft_ai",
        "sourceUrl": "https://x.com/Popcraft_ai/status/2051142270381170754",
        "prompt": "Inspired by Tsingtao beer, design a cool-style women's clothing collection.",
        "category": "Products & E-commerce",
        "styles": ["Product"],
        "scenes": ["Commerce", "Fashion"],
        "githubUrl": "https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-385",
    }
    payload.update(overrides)
    return payload


def test_case_dedupe_keys_include_status_url_case_and_prompt_hash():
    case = _case(sourceUrl="https://x.com/Popcraft_ai/status/2051142270381170754?s=20")

    keys = case_dedupe_keys(case)

    assert "canghe_case:385" in keys
    assert "x_status:2051142270381170754" in keys
    assert "source_url:https://x.com/Popcraft_ai/status/2051142270381170754" in keys
    assert f"prompt_sha256:{prompt_hash(case['prompt'])}" in keys


def test_select_new_cases_skips_previous_x_status_imports(tmp_path: Path):
    repo = ItemRepository(tmp_path / "library")
    repo.create_item(
        ItemCreate(
            title="Existing X import",
            source_url="https://x.com/Popcraft_ai/status/2051142270381170754?s=20",
            prompts=[PromptIn(language="en", text="Earlier manually absorbed prompt.", is_primary=True)],
        ),
        imported=True,
    )
    with connect(tmp_path / "library") as conn:
        existing_keys = {
            f"x_status:{row[0]}"
            for row in conn.execute("SELECT '2051142270381170754'").fetchall()
        }
    cases = [
        _case(),
        _case(
            id=386,
            sourceUrl="https://x.com/new/status/2052000000000000000",
            prompt="A new incremental prompt from the Canghe gallery feed.",
        ),
    ]

    selected, duplicate_count = select_new_cases(cases, existing_keys)

    assert duplicate_count == 1
    assert [case["id"] for case in selected] == [386]


def test_no_image_existing_prompt_hash_does_not_block_image_backfill(tmp_path: Path):
    repo = ItemRepository(tmp_path / "library")
    repo.create_item(
        ItemCreate(
            title="No image exact prompt",
            source_url="https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-385",
            prompts=[PromptIn(language="en", text=_case()["prompt"], is_primary=True)],
        ),
        imported=True,
    )

    existing_keys = collect_existing_dedupe_keys(tmp_path / "library")
    selected, duplicate_count = select_new_cases([_case()], existing_keys)

    assert duplicate_count == 0
    assert [case["id"] for case in selected] == [385]


def test_item_payload_preserves_source_and_gallery_tags():
    payload = item_payload_for_case(_case())

    assert payload.slug == "canghe-gpt-image-2-case-385"
    assert payload.model == "GPT Image 2"
    assert payload.cluster_name == "Products & E-commerce"
    assert payload.author == "@Popcraft_ai"
    assert payload.source_url == "https://x.com/Popcraft_ai/status/2051142270381170754"
    assert payload.tags == [
        "canghe-gallery",
        "awesome-gpt-image-2",
        "GPT Image 2",
        "Products & E-commerce",
        "Product",
        "Commerce",
        "Fashion",
    ]
    assert payload.prompts[0].language == "en"
    assert "Canghe gallery case id: 385" in (payload.notes or "")
    assert image_url_for_case(_case()) == "https://gpt-image2.canghe.ai/images/case385.jpg"


def test_sync_canghe_gallery_imports_incremental_case_with_image(tmp_path: Path):
    library = tmp_path / "library"
    cases_payload = {"totalCases": 1, "cases": [_case(image="/images/case385.png")]}

    result = sync_canghe_gallery(
        library,
        cases_payload=cases_payload,
        image_fetcher=lambda url: _png_bytes(),
    )

    assert result.imported_count == 1
    assert result.image_count == 1
    assert result.failures == []
    imported = result.imported_items[0]
    assert imported.case_id == "385"
    assert imported.image_url == "https://gpt-image2.canghe.ai/images/case385.png"
    detail = ItemRepository(library).get_item(imported.item_id)
    assert detail.title == "Qingdao Beer Fashion Set"
    assert detail.images and (library / detail.images[0].thumb_path).exists()
    assert {tag.name for tag in detail.tags} >= {"canghe-gallery", "Fashion"}


def test_sync_canghe_gallery_archives_legacy_no_image_duplicate_after_import(tmp_path: Path):
    library = tmp_path / "library"
    repo = ItemRepository(library)
    legacy = repo.create_item(
        ItemCreate(
            title="Qingdao Beer Fashion Set",
            source_name="freestylefly/awesome-gpt-image-2",
            source_url="https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-385",
            notes="Imported from freestylefly/awesome-gpt-image-2. Original case: https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-385",
            prompts=[PromptIn(language="en", text="Legacy English-only prompt.", is_primary=True)],
        ),
        imported=True,
    )

    result = sync_canghe_gallery(
        library,
        cases_payload={"totalCases": 1, "cases": [_case(image="/images/case385.png")]},
        image_fetcher=lambda _url: _png_bytes(),
    )

    assert result.imported_count == 1
    assert result.archived_duplicate_count == 1
    assert repo.get_item(legacy.id).archived is True
    assert repo.list_items(limit=10).total == 1


def test_sync_canghe_gallery_archives_no_image_duplicate_by_x_status_after_import(tmp_path: Path):
    library = tmp_path / "library"
    repo = ItemRepository(library)
    legacy = repo.create_item(
        ItemCreate(
            title="Qingdao Beer Fashion Set",
            source_name="X / Popcraft",
            source_url="https://x.com/Popcraft_ai/status/2051142270381170754?s=20",
            prompts=[PromptIn(language="en", text="Previously absorbed without an image.", is_primary=True)],
        ),
        imported=True,
    )

    result = sync_canghe_gallery(
        library,
        cases_payload={"totalCases": 1, "cases": [_case(image="/images/case385.png")]},
        image_fetcher=lambda _url: _png_bytes(),
    )

    assert result.imported_count == 1
    assert result.archived_duplicate_count == 1
    assert repo.get_item(legacy.id).archived is True


def test_canghe_gallery_sync_endpoint_requires_admin_and_supports_password_payload(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / "library")
    client = TestClient(app)

    def fake_sync(*_args, **kwargs):
        from backend.schemas import CangheGallerySyncResponse

        return CangheGallerySyncResponse(
            source_url="https://gpt-image2.canghe.ai/cases.json",
            source_total=382,
            duplicate_count=381,
            candidate_count=1,
            dry_run=kwargs["dry_run"],
            max_imports=kwargs["max_imports"],
        )

    monkeypatch.setattr("backend.routers.intake.sync_canghe_gallery", fake_sync)

    unauthorized = client.post("/api/admin/intake/canghe-gallery/sync", json={"dry_run": True})
    authorized = client.post(
        "/api/admin/intake/canghe-gallery/sync",
        json={"admin_password": ADMIN_PASSWORD, "dry_run": True, "max_imports": 1},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["candidate_count"] == 1
    assert authorized.json()["dry_run"] is True
