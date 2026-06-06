import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_github_pages_demo_mode_uses_static_data_and_base_path():
    vite_config = (ROOT / "vite.config.ts").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    demo = (ROOT / "frontend" / "src" / "api" / "demo.ts").read_text()
    media = (ROOT / "frontend" / "src" / "api" / "media.ts").read_text()
    package_json = (ROOT / "package.json").read_text()

    assert "VITE_BASE_PATH" in vite_config
    assert "base:" in vite_config
    assert "VITE_DEMO_MODE" in demo
    assert "VITE_DEMO_ASSET_VERSION" in demo
    assert "DEMO_DATA_BASE" in client
    assert "demo-data/items.json" in demo
    assert "demo-data/clusters.json" in demo
    assert "demo-data/tags.json" in demo
    assert "mediaUrl = (path?: string)" in media
    assert "demoUrl" in demo
    assert '"build:demo"' in package_json
    assert "VITE_DEMO_MODE=true" in package_json
    assert "VITE_BASE_PATH=/" in package_json


def test_github_pages_demo_is_read_only_and_discloses_compressed_images():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "isDemoMode" in app
    assert "demo-banner" in app
    assert "onlineSandbox" in i18n
    assert "readOnlySampleLibrary" in i18n
    assert "compressedForDemo" in i18n
    assert "runLocallyForPrivateLibrary" in i18n
    assert "showActions" in cards
    assert "showMutations" in detail
    assert "!isDemoMode && <button className=\"fab\"" in app
    assert "onAdd={isDemoMode ? undefined : openNewItemEditor}" in app
    assert "onFavorite={isDemoMode ? undefined : favorite}" in app
    assert "onEdit={isDemoMode ? undefined : editSummary}" in app


def test_github_pages_workflow_deploys_versioned_demo_builds():
    workflow = ROOT / ".github" / "workflows" / "pages.yml"
    assert workflow.exists()
    text = workflow.read_text()
    assert "actions/configure-pages" in text
    assert "actions/upload-pages-artifact" in text
    assert "actions/deploy-pages" in text
    assert "fetch-depth: 0" in text
    assert "LEGACY_DEMO_REF: v0.1.0-alpha" in text
    assert "CUSTOM_DOMAIN: prompt.wendealai.com" in text
    assert "MOBILE_PREVIEW_PATH: v0.2" in text
    assert "VITE_DEMO_ASSET_VERSION=${GITHUB_SHA}" in text
    assert "VITE_BASE_PATH=/ npm run build" in text
    assert "git worktree add .page-build/${LEGACY_DEMO_PATH} ${LEGACY_DEMO_REF}" in text
    assert "VITE_BASE_PATH=/${LEGACY_DEMO_PATH}/ npm run build" in text
    assert ".pages-artifact/${MOBILE_PREVIEW_PATH}" in text
    assert ".pages-artifact/${LEGACY_DEMO_PATH}" in text
    assert 'echo "${CUSTOM_DOMAIN}" > .pages-artifact/CNAME' in text
    assert "path: .pages-artifact" in text


def test_package_exposes_versioned_demo_build_scripts():
    package_json = (ROOT / "package.json").read_text()
    assert '"build:demo:v0.1"' in package_json
    assert '"build:demo:v0.2"' in package_json
    assert "VITE_BASE_PATH=/v0.1/" in package_json
    assert "VITE_BASE_PATH=/v0.2/" in package_json


def test_demo_export_script_outputs_compact_static_assets():
    script = ROOT / "scripts" / "export-demo-data.py"
    assert script.exists()
    text = script.read_text()
    assert "frontend/public/demo-data" in text
    assert "DEMO_IMAGE_MAX_WIDTH" in text
    assert "DEMO_IMAGE_QUALITY" in text
    assert "compressed" in text.lower()
    assert "items.json" in text
    assert "clusters.json" in text
    assert "tags.json" in text


def test_demo_data_bundle_is_present_and_uses_compressed_media_paths():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    assert (demo_root / "items.json").exists()
    assert (demo_root / "clusters.json").exists()
    assert (demo_root / "tags.json").exists()
    items_text = (demo_root / "items.json").read_text()
    assert "demo-data/media/" in items_text
    assert ".webp" in items_text
    assert "originals/" not in items_text
    assert "library/db.sqlite" not in items_text


def test_demo_bundle_metadata_and_taxonomy_counts_match_items():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items = json.loads((demo_root / "items.json").read_text())
    tags = json.loads((demo_root / "tags.json").read_text())
    clusters = json.loads((demo_root / "clusters.json").read_text())
    metadata = json.loads((demo_root / "metadata.json").read_text())

    assert metadata["item_count"] == len(items)

    expected_tag_counts = Counter(
        tag["name"]
        for item in items
        for tag in item.get("tags", [])
    )
    for tag in tags:
        assert tag["count"] == expected_tag_counts.get(tag["name"], 0)

    expected_cluster_counts = Counter()
    expected_previews = defaultdict(list)
    for item in items:
        cluster = item.get("cluster")
        if not cluster:
            continue
        cluster_id = cluster["id"]
        expected_cluster_counts[cluster_id] += 1
        first_image = item.get("first_image")
        if not first_image or len(expected_previews[cluster_id]) >= 4:
            continue
        preview = first_image.get("thumb_path") or first_image.get("preview_path") or first_image.get("remote_url")
        if preview:
            expected_previews[cluster_id].append(preview)

    for cluster in clusters:
        assert cluster["count"] == expected_cluster_counts.get(cluster["id"], 0)
        assert cluster["preview_images"] == expected_previews.get(cluster["id"], [])

    image_less = [
        item["slug"]
        for item in items
        if not item.get("first_image")
        or not any(item["first_image"].get(key) for key in ("thumb_path", "preview_path", "original_path", "remote_url"))
    ]
    assert image_less == []



def test_demo_bundle_matches_latest_production_export_counts():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items = json.loads((demo_root / "items.json").read_text())
    clusters = json.loads((demo_root / "clusters.json").read_text())
    tags = json.loads((demo_root / "tags.json").read_text())
    metadata = json.loads((demo_root / "metadata.json").read_text())
    media_files = list((demo_root / "media").glob("*.webp"))

    assert len(items) == 1121
    assert len(clusters) == 172
    assert len(tags) == 2085
    assert len(media_files) == 1892
    assert metadata["item_count"] == 1121
    assert metadata["image_max_width"] == 900
    assert metadata["image_quality"] == 62


def test_demo_bundle_media_references_resolve_to_tracked_webp_files():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items = json.loads((demo_root / "items.json").read_text())
    clusters = json.loads((demo_root / "clusters.json").read_text())
    media_dir = demo_root / "media"
    referenced = set()

    def visit(value):
        if isinstance(value, str) and value.startswith("demo-data/media/"):
            referenced.add(value.rsplit("/", 1)[-1])
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(items)
    visit(clusters)

    media_files = {path.name for path in media_dir.glob("*.webp")}

    assert len(referenced) == 1892
    assert referenced <= media_files


def test_demo_bundle_uses_local_media_for_x_imports():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items = json.loads((demo_root / "items.json").read_text())

    x_imports = [item for item in items if (item.get("source_url") or "").startswith("https://x.com/")]
    assert len(x_imports) == 678
    for item in x_imports:
        first_image = item["first_image"]
        assert first_image["original_path"].startswith("demo-data/media/")
        assert first_image["thumb_path"].startswith("demo-data/media/")
        assert first_image["preview_path"].startswith("demo-data/media/")
        assert first_image["remote_url"] is None


def test_demo_bundle_includes_latest_production_and_sample_records():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "https://x.com/michaelrabone/status/2062897234551751078" in items_text
    assert "https://x.com/SimplyAnnisa/status/2062900307898646713" in items_text
    assert "https://x.com/xiaoxiaodong01/status/2062909486730444929" in items_text
    assert "https://x.com/AIwithSynthia/status/2062521441141088599" in items_text
    assert "飞翔感中文字体设计视觉" in items_text
    assert "High-End Marketplace Brand Campaign Prompt" in items_text
    assert "Coffee Breeze Desk Afternoon Prompt" in items_text
    assert "demo-data/media/" in items_text
