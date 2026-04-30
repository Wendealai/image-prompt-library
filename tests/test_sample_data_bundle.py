import json
import os
import subprocess
import sys
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


import pytest
from PIL import Image

from backend.services import import_demo_bundle as import_demo_bundle_module
from backend.repositories import ItemRepository
from backend.services.import_demo_bundle import import_demo_bundle
from backend.services.import_sample_bundle import import_sample_bundle

ROOT = Path(__file__).resolve().parents[1]


def _write_demo_bundle(bundle_root: Path) -> None:
    media_dir = bundle_root / "media"
    media_dir.mkdir(parents=True)
    Image.new("RGB", (24, 18), "green").save(media_dir / "fixture.webp", "WEBP")
    (bundle_root / "items.json").write_text(json.dumps([{
        "id": "itm_demo_fixture",
        "title": "Demo fixture",
        "slug": "demo-fixture",
        "model": "Demo model",
        "source_name": "fixture source",
        "source_url": "https://example.test/demo",
        "cluster": {"id": "clu_demo", "name": "Demo Cases", "description": None, "sort_order": 0, "count": 0, "preview_images": []},
        "tags": [{"id": "tag_demo", "name": "sample", "kind": "general", "count": 0}],
        "prompts": [{"language": "en", "text": "A green square", "is_primary": True}],
        "prompt_snippet": "A green square",
        "first_image": {
            "id": "img_demo_fixture",
            "item_id": "itm_demo_fixture",
            "original_path": "demo-data/media/fixture.webp",
            "thumb_path": "demo-data/media/fixture.webp",
            "preview_path": "demo-data/media/fixture.webp",
            "remote_url": None,
            "width": 24,
            "height": 18,
            "file_sha256": None,
            "role": "result_image",
            "sort_order": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        "rating": 4,
        "favorite": False,
        "archived": False,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "images": [{
            "id": "img_demo_fixture",
            "item_id": "itm_demo_fixture",
            "original_path": "demo-data/media/fixture.webp",
            "thumb_path": "demo-data/media/fixture.webp",
            "preview_path": "demo-data/media/fixture.webp",
            "remote_url": None,
            "width": 24,
            "height": 18,
            "file_sha256": None,
            "role": "result_image",
            "sort_order": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
        }],
        "notes": "Fixture notes",
        "author": "Fixture Author",
    }]), encoding="utf-8")


class _QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # pragma: no cover - test noise only
        pass


def test_sample_data_manifests_are_localized_and_truthful():
    manifest_dir = ROOT / "sample-data" / "manifests"
    manifests = {lang: json.loads((manifest_dir / f"{lang}.json").read_text()) for lang in ("en", "zh_hans", "zh_hant")}

    assert set(manifests) == {"en", "zh_hans", "zh_hant"}
    assert len(manifests["en"]["items"]) == 162
    assert len(manifests["zh_hans"]["items"]) == 162
    assert len(manifests["zh_hant"]["items"]) == 162
    assert len(manifests["en"]["collections"]) == 10
    assert {collection["id"] for collection in manifests["en"]["collections"]} == {
        collection["id"] for collection in manifests["zh_hant"]["collections"]
    }
    assert "wuyoscar/gpt_image_2_skill" in manifests["en"]["source"]["name"]
    assert manifests["en"]["source"]["license"] == "CC BY 4.0"

    zh_hant_fallback_ids = {
        item["id"]
        for item in manifests["zh_hant"]["items"]
        if item["prompts"] and {prompt["language"] for prompt in item["prompts"]} == {"en"}
    }
    zh_hans_fallback_ids = {
        item["id"]
        for item in manifests["zh_hans"]["items"]
        if item["prompts"] and {prompt["language"] for prompt in item["prompts"]} == {"en"}
    }
    assert zh_hant_fallback_ids, "sample data should keep English-only source entries as English instead of inventing Chinese prompts"
    assert zh_hant_fallback_ids == zh_hans_fallback_ids


def test_sample_data_attribution_documents_third_party_license_boundary():
    attribution = (ROOT / "sample-data" / "ATTRIBUTION.md").read_text()
    readme = (ROOT / "sample-data" / "README.md").read_text()

    assert "wuyoscar/gpt_image_2_skill" in attribution
    assert "CC BY 4.0" in attribution
    assert "No additional restrictions" in attribution
    assert "The Image Prompt Library code license does not apply" in attribution
    assert "sample-data-v1" in readme
    assert "image-prompt-library-sample-images-v1.zip" in readme
    assert "SHA256" in readme
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in readme
    assert "./scripts/install-sample-data.sh en" in readme


def test_import_sample_bundle_loads_manifest_assets_and_is_idempotent(tmp_path: Path):
    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "one.png"
    Image.new("RGB", (16, 12), "red").save(image_path)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "id": "fixture-sample",
        "language": "zh_hant",
        "source": {"name": "fixture", "license": "CC BY 4.0"},
        "collections": [{"id": "visual", "name": "視覺設計", "names": {"en": "Visual Design", "zh_hant": "視覺設計"}}],
        "items": [{
            "id": "fixture-001",
            "title": "Fixture image",
            "slug": "fixture-image",
            "collection_id": "visual",
            "image": "images/one.png",
            "source_name": "fixture source",
            "source_url": "https://example.test/source",
            "author": "fixture author",
            "license": "CC BY 4.0",
            "tags": ["sample"],
            "prompts": [{"language": "zh_hant", "text": "一個紅色方塊", "is_primary": True}],
        }],
    }), encoding="utf-8")

    first = import_sample_bundle(manifest, assets, tmp_path / "library")
    second = import_sample_bundle(manifest, assets, tmp_path / "library")

    assert first.item_count == 1
    assert first.image_count == 1
    assert second.item_count == 0
    assert second.image_count == 0
    items = ItemRepository(tmp_path / "library").list_items(limit=10).items
    assert len(items) == 1
    assert items[0].cluster.name == "視覺設計"
    assert items[0].first_image is not None
    assert items[0].prompts[0].language == "zh_hant"
    detail = ItemRepository(tmp_path / "library").get_item(items[0].id)
    assert detail is not None
    assert "CC BY 4.0" in (detail.notes or "")
    assert "Original source URL" not in (detail.notes or "")
    assert "Original source file" not in (detail.notes or "")
    assert len(detail.notes or "") < 180


def test_import_demo_bundle_loads_local_demo_bundle_and_is_idempotent(tmp_path: Path):
    bundle = tmp_path / "demo-data"
    _write_demo_bundle(bundle)

    first = import_demo_bundle(bundle, tmp_path / "library")
    second = import_demo_bundle(bundle, tmp_path / "library")

    assert first.item_count == 1
    assert first.image_count == 1
    assert second.item_count == 0
    assert second.image_count == 0

    repo = ItemRepository(tmp_path / "library")
    items = repo.list_items(limit=10).items
    assert len(items) == 1
    assert items[0].cluster is not None
    assert items[0].cluster.name == "Demo Cases"
    detail = repo.get_item(items[0].id)
    assert detail.first_image is not None
    assert detail.prompts[0].language == "en"
    assert detail.prompts[0].text == "A green square"
    assert detail.notes == "Fixture notes"


def test_import_demo_bundle_supports_remote_demo_bundle_url(tmp_path: Path):
    site_root = tmp_path / "site"
    bundle = site_root / "demo-data"
    _write_demo_bundle(bundle)

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHTTPRequestHandler, directory=str(site_root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = import_demo_bundle(f"http://127.0.0.1:{server.server_port}/demo-data", tmp_path / "library")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert result.item_count == 1
    assert result.image_count == 1
    detail = ItemRepository(tmp_path / "library").get_item("itm_demo_fixture")
    assert detail.first_image is not None
    assert detail.first_image.original_path.startswith("originals/")


def test_import_demo_bundle_cli_public_flag_uses_public_bundle_url(tmp_path: Path, monkeypatch, capsys):
    site_root = tmp_path / "site"
    bundle = site_root / "demo-data"
    _write_demo_bundle(bundle)

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHTTPRequestHandler, directory=str(site_root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(
            import_demo_bundle_module,
            "DEFAULT_PUBLIC_V0_1_BUNDLE_URL",
            f"http://127.0.0.1:{server.server_port}/demo-data",
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["import-demo-data.py", "--public-v0.1", "--library", str(tmp_path / "library")],
        )
        import_demo_bundle_module.main()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    output = capsys.readouterr().out
    assert '"item_count": 1' in output
    assert '"image_count": 1' in output


def test_install_sample_data_script_verifies_release_zip_checksum():
    installer = (ROOT / "scripts" / "install-sample-data.sh").read_text()

    assert "EXPECTED_SHA256" in installer
    assert "sha256sum" in installer or "shasum -a 256" in installer
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in installer


def test_install_sample_data_script_supports_local_zip_override(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("install-sample-data.sh is a POSIX shell script; Windows cannot execute it directly.")
    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), "blue").save(image_dir / "fixture.png")
    manifest = tmp_path / "fixture-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "id": "fixture-installer",
        "language": "en",
        "source": {"name": "fixture", "license": "CC BY 4.0"},
        "collections": [{"id": "demo", "name": "Demo", "names": {"en": "Demo"}}],
        "items": [{
            "id": "fixture-installer-001",
            "title": "Installer fixture",
            "slug": "installer-fixture",
            "collection_id": "demo",
            "image": "images/fixture.png",
            "source_name": "fixture",
            "tags": ["sample"],
            "prompts": [{"language": "en", "text": "A blue square", "is_primary": True}],
        }],
    }), encoding="utf-8")
    zip_path = tmp_path / "sample-images.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(image_dir / "fixture.png", "images/fixture.png")

    library = tmp_path / "library"
    result = subprocess.run(
        [str(ROOT / "scripts" / "install-sample-data.sh"), "en"],
        cwd=ROOT,
        env={
            **os.environ,
            "IMAGE_PROMPT_LIBRARY_PATH": str(library),
            "PYTHON": sys.executable,
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
        },
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Imported 1 items" in result.stdout
    assert ItemRepository(library).list_items(limit=5).total == 1


def test_import_demo_data_script_exposes_local_and_public_v0_1_bundle_options():
    script = (ROOT / "scripts" / "import-demo-data.py").read_text()

    assert "import_demo_bundle" in script
    assert ".venv" in script
    service = (ROOT / "backend" / "services" / "import_demo_bundle.py").read_text()
    assert 'ROOT / "frontend" / "public" / "demo-data"' in service
    assert "https://eddietyp.github.io/image-prompt-library/v0.1/demo-data" in service
