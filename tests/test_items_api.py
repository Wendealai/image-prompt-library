import os

import pytest
from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image
from backend.config import APP_VERSION
from backend.main import create_app
from backend.db import connect
from backend.repositories import ItemRepository, StoredImageInput
from backend.schemas import ItemCreate


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def png_bytes(size=(32, 24), color=(120, 40, 220)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def create_payload(**overrides):
    payload = {
        "title": "Dream Glass Teahouse",
        "model": "ChatGPT Image2",
        "cluster_name": "Architecture",
        "tags": ["glass", "vista"],
        "prompts": [
            {"language": "zh_hant", "text": "夢幻玻璃茶室，晨光穿過霧氣", "is_primary": True},
            {"language": "en", "text": "A dreamy glass teahouse in morning mist"},
        ],
        "source_name": "fixture",
        "source_url": "https://example.test/item",
    }
    payload.update(overrides)
    return payload


def test_create_get_search_and_filter_item(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    assert created["title"] == "Dream Glass Teahouse"
    assert created["cluster"]["name"] == "Architecture"
    assert created["use_case"] == "场景空间"
    assert {t["name"] for t in created["tags"]} == {"glass", "vista"}

    detail = c.get(f"/api/items/{created['id']}").json()
    assert len(detail["prompts"]) == 2
    listed = c.get("/api/items").json()["items"][0]
    assert {p["language"]: p["text"] for p in listed["prompts"]} == {
        "zh_hant": "夢幻玻璃茶室，晨光穿過霧氣",
        "en": "A dreamy glass teahouse in morning mist",
    }

    assert c.get("/api/items", params={"q": "Teahouse"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "玻璃茶室"}).json()["total"] == 1
    assert c.get("/api/items", params={"q": "morning mist"}).json()["total"] == 1
    assert c.get("/api/items", params={"tag": "vista"}).json()["total"] == 1
    assert c.get("/api/items", params={"cluster": created["cluster"]["id"]}).json()["total"] == 1
    assert c.get("/api/items", params={"use_case": "场景空间"}).json()["total"] == 1


def test_use_case_catalog_and_filter_cover_distinct_prompt_families(tmp_path):
    c = client(tmp_path)
    portrait = c.post("/api/items", json=create_payload(
        title="Luxury Beauty Portrait",
        cluster_name="Photography & Realism",
        tags=["beauty", "portrait"],
        prompts=[{"language": "en", "text": "A luxury beauty portrait close-up of a fashion model", "is_primary": True}],
    )).json()
    dashboard = c.post("/api/items", json=create_payload(
        title="Minimal Finance Dashboard UI",
        cluster_name="UI & Interfaces",
        tags=["ui", "dashboard"],
        prompts=[{"language": "en", "text": "A polished SaaS finance dashboard interface", "is_primary": True}],
        source_url="https://example.test/dashboard",
    )).json()
    poster = c.post("/api/items", json=create_payload(
        title="Bold Film Poster",
        cluster_name="Posters & Typography",
        tags=["poster", "typography"],
        prompts=[{"language": "en", "text": "A bold cinematic poster with oversized typography", "is_primary": True}],
        source_url="https://example.test/poster",
    )).json()

    assert portrait["use_case"] == "人物肖像"
    assert dashboard["use_case"] == "界面设计"
    assert poster["use_case"] == "海报视觉"

    use_cases = c.get("/api/use-cases").json()
    assert {record["name"] for record in use_cases} >= {"人物肖像", "界面设计", "海报视觉"}
    assert c.get("/api/items", params={"use_case": "界面设计"}).json()["items"][0]["id"] == dashboard["id"]
    assert c.get("/api/items", params={"use_case": "海报视觉"}).json()["items"][0]["id"] == poster["id"]


def test_item_tags_keep_payload_order_on_create_and_update(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(tags=["zebra", "alpha", "mid"])).json()
    assert [tag["name"] for tag in created["tags"]] == ["zebra", "alpha", "mid"]

    patched = c.patch(f"/api/items/{created['id']}", json={"tags": ["glass", "cinematic", "poster"]}).json()
    assert [tag["name"] for tag in patched["tags"]] == ["glass", "cinematic", "poster"]

    listed = c.get("/api/items", params={"sort": "created_desc"}).json()["items"][0]
    assert [tag["name"] for tag in listed["tags"]] == ["glass", "cinematic", "poster"]


def test_items_list_limit_allows_gallery_overview_scale(tmp_path):
    c = client(tmp_path)
    for idx in range(230):
        c.post("/api/items", json=create_payload(title=f"Overview Item {idx}", cluster_name=f"Cluster {idx % 7}"))
    listed = c.get("/api/items", params={"limit": 300}).json()
    assert listed["total"] == 230
    assert listed["limit"] == 300
    assert len(listed["items"]) == 230


def test_items_created_desc_order_is_stable_with_id_tiebreaker(tmp_path):
    repository = ItemRepository(tmp_path / "library")
    shared_created_at = "2026-01-01T00:00:00+00:00"
    first = repository.create_item(ItemCreate.model_validate(create_payload(title="Stable Order A")))
    second = repository.create_item(ItemCreate.model_validate(create_payload(title="Stable Order B", source_url="https://example.test/b")))
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE items SET created_at=?, updated_at=? WHERE id IN (?, ?)", (shared_created_at, shared_created_at, first.id, second.id))
        conn.commit()

    listed = repository.list_items(sort="created_desc", limit=10, offset=0)

    assert [item.id for item in listed.items[:2]] == sorted([first.id, second.id], reverse=True)


def test_patch_favorite_and_archive_item(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    c.post(
        f"/api/items/{created['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    patched = c.patch(f"/api/items/{created['id']}", json={"title": "Updated", "favorite": True, "rating": 4}).json()
    assert patched["title"] == "Updated"
    assert patched["favorite"] is True
    assert patched["rating"] == 4
    toggled = c.post(f"/api/items/{created['id']}/favorite").json()
    assert toggled["favorite"] is False
    deleted = c.delete(f"/api/items/{created['id']}").json()
    assert deleted["archived"] is True
    assert c.get("/api/items").json()["total"] == 0
    assert c.get("/api/items", params={"archived": True}).json()["total"] == 1
    assert c.get("/api/clusters").json() == []
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] == 0
    assert {tag["name"]: tag["count"] for tag in c.get("/api/tags").json()} == {"glass": 0, "vista": 0}


def test_clusters_tags_and_config(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    clusters = c.get("/api/clusters").json()
    assert clusters[0]["name"] == "Architecture"
    assert clusters[0]["count"] == 1
    tags = c.get("/api/tags").json()
    assert {t["name"] for t in tags} >= {"glass", "vista"}
    cfg = c.get("/api/config").json()
    assert cfg["version"] == APP_VERSION
    assert cfg["database_path"].endswith("db.sqlite")
    assert c.get("/api/health").json()["ok"] is True


def test_media_route_does_not_expose_database(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    assert c.get("/media/db.sqlite").status_code == 404


def test_media_route_serves_webp_with_image_mime_type(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    c.post(
        f"/api/items/{created['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    detail = c.get(f"/api/items/{created['id']}").json()
    response = c.get(f"/media/{detail['first_image']['thumb_path']}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")


def test_image_download_route_returns_original_as_attachment(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload()).json()
    c.post(
        f"/api/items/{created['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    detail = c.get(f"/api/items/{created['id']}").json()
    image = detail["first_image"]
    response = c.get(f"/api/items/{created['id']}/images/{image['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert "attachment" in response.headers["content-disposition"]
    assert image["id"] in response.headers["content-disposition"]


def test_media_route_does_not_follow_allowed_dir_symlink_to_database(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    library = tmp_path / "library"
    db_path = library / "db.sqlite"
    assert db_path.exists()
    leak = library / "originals" / "leak"
    leak.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(db_path), str(leak))
    except OSError as exc:
        pytest.skip(f"symlink creation is not available in this environment: {exc}")
    assert c.get("/media/originals/leak").status_code == 404


def test_punctuation_only_search_does_not_error(tmp_path):
    c = client(tmp_path)
    c.post("/api/items", json=create_payload())
    response = c.get("/api/items", params={"q": '"'})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_missing_item_mutations_return_404(tmp_path):
    c = client(tmp_path)
    assert c.delete("/api/items/missing").status_code == 404
    assert c.post("/api/items/missing/favorite").status_code == 404
    assert c.patch("/api/items/missing", json={"tags": ["ghost"]}).status_code == 404
    assert c.patch("/api/items/missing", json={"prompts": [{"language": "en", "text": "ghost"}]}).status_code == 404


def test_upload_to_missing_item_returns_404_without_orphan_files(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/items/missing/images", files={"file": ("sample.png", b"not an image", "image/png")})
    assert response.status_code == 404
    library = tmp_path / "library"
    assert not [p for name in ("originals", "thumbs", "previews") if (library / name).exists() for p in (library / name).rglob("*")]


def test_image_upload_persists_result_and_reference_roles(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    result = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(), "image/png")},
    )
    reference = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "reference_image"},
        files={"file": ("reference.png", png_bytes(color=(1, 2, 3)), "image/png")},
    )
    invalid = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "other"},
        files={"file": ("other.png", png_bytes(color=(4, 5, 6)), "image/png")},
    )
    detail = c.get(f"/api/items/{item['id']}").json()
    assert result.status_code == 200
    assert reference.status_code == 200
    assert invalid.status_code == 400
    assert [image["role"] for image in detail["images"]] == ["result_image", "reference_image"]


def test_delete_remote_generated_image_removes_record_without_file_error(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    repository = ItemRepository(tmp_path / "library")
    remote_image = repository.add_remote_image(item["id"], "https://cdn.example.test/generated/result.png")

    response = c.delete(f"/api/items/{item['id']}/images/{remote_image.id}")

    assert response.status_code == 200
    assert response.json()["images"] == []
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM images WHERE id=?", (remote_image.id,)).fetchone()[0] == 0


def test_generated_image_history_lists_workflow_and_direct_results(tmp_path):
    c = client(tmp_path)
    workflow_item = c.post("/api/items", json=create_payload(title="Aurora Frame", cluster_name="Architecture")).json()
    direct_item = c.post("/api/items", json=create_payload(title="Morning Poster", cluster_name="Portrait", source_url="https://example.test/direct")).json()
    repository = ItemRepository(tmp_path / "library")
    workflow_image = repository.add_remote_image(workflow_item["id"], "https://cdn.example.test/generated/workflow.png")
    repository.add_prompt_image_generation_run(
        item_id=workflow_item["id"],
        prompt="Aurora glass tower prompt",
        references=[{"label": "mood"}],
        image_ids=[workflow_image.id],
    )
    direct_image = repository.add_remote_image(direct_item["id"], "https://cdn.example.test/generated/direct.png")

    listed = c.get("/api/generated-image-history", params={"limit": 10}).json()
    by_image_id = {entry["image"]["id"]: entry for entry in listed["items"]}

    assert listed["total"] == 2
    assert by_image_id[workflow_image.id]["item_title"] == "Aurora Frame"
    assert by_image_id[workflow_image.id]["source"] == "workflow"
    assert by_image_id[workflow_image.id]["run"]["image_ids"] == [workflow_image.id]
    assert by_image_id[direct_image.id]["item_title"] == "Morning Poster"
    assert by_image_id[direct_image.id]["source"] == "direct"
    assert by_image_id[direct_image.id]["run"] is None

    searched = c.get("/api/generated-image-history", params={"q": "Aurora"}).json()
    assert searched["total"] == 1
    assert searched["items"][0]["item_id"] == workflow_item["id"]

    filtered = c.get("/api/generated-image-history", params={"cluster": "Portrait"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["item_id"] == direct_item["id"]


def test_delete_shared_local_image_keeps_file_until_last_record(tmp_path):
    c = client(tmp_path)
    first = c.post("/api/items", json=create_payload(title="First")).json()
    second = c.post("/api/items", json=create_payload(title="Second", source_url="https://example.test/second")).json()
    uploaded = c.post(
        f"/api/items/{first['id']}/images",
        data={"role": "result_image"},
        files={"file": ("shared.png", png_bytes(), "image/png")},
    ).json()
    repository = ItemRepository(tmp_path / "library")
    duplicate = repository.add_image(
        second["id"],
        StoredImageInput(
            uploaded["original_path"],
            uploaded["thumb_path"],
            uploaded["preview_path"],
            width=uploaded["width"],
            height=uploaded["height"],
            role="result_image",
        ),
    )
    original_path = tmp_path / "library" / uploaded["original_path"]

    response = c.delete(f"/api/items/{first['id']}/images/{uploaded['id']}")

    assert response.status_code == 200
    assert original_path.exists()
    assert duplicate.original_path == uploaded["original_path"]


def test_result_image_is_primary_even_when_reference_uploaded_first(tmp_path):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    reference = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "reference_image"},
        files={"file": ("reference.png", png_bytes(color=(1, 2, 3)), "image/png")},
    ).json()
    result = c.post(
        f"/api/items/{item['id']}/images",
        data={"role": "result_image"},
        files={"file": ("result.png", png_bytes(color=(4, 5, 6)), "image/png")},
    ).json()

    listed = c.get("/api/items").json()["items"][0]
    detail = c.get(f"/api/items/{item['id']}").json()
    cluster = c.get("/api/clusters").json()[0]

    assert reference["role"] == "reference_image"
    assert result["role"] == "result_image"
    assert listed["first_image"]["id"] == result["id"]
    assert detail["first_image"]["id"] == result["id"]
    assert detail["images"][0]["id"] == result["id"]
    assert cluster["preview_images"] == [result["thumb_path"]]


def test_editing_last_item_out_of_collection_removes_empty_collection(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(cluster_name="Old Collection")).json()
    assert [cluster["name"] for cluster in c.get("/api/clusters").json()] == ["Old Collection"]

    patched = c.patch(f"/api/items/{created['id']}", json={"cluster_name": "New Collection"}).json()

    assert patched["cluster"]["name"] == "New Collection"
    assert [cluster["name"] for cluster in c.get("/api/clusters").json()] == ["New Collection"]
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT name FROM clusters").fetchall()[0]["name"] == "New Collection"


def test_listing_clusters_removes_existing_archived_only_collections(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(cluster_name="Legacy Empty Collection")).json()
    c.delete(f"/api/items/{created['id']}")
    with connect(tmp_path / "library") as conn:
        archived_cluster_id = conn.execute("SELECT cluster_id FROM items WHERE id=?", (created["id"],)).fetchone()["cluster_id"]
        old_name = "Legacy Empty Collection"
        conn.execute("INSERT INTO clusters(id, name, created_at, updated_at) VALUES(?, ?, datetime('now'), datetime('now'))", (archived_cluster_id or "clu_legacy_empty", old_name))
        conn.execute("UPDATE items SET cluster_id=? WHERE id=?", (archived_cluster_id or "clu_legacy_empty", created["id"]))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM clusters WHERE name=?", (old_name,)).fetchone()[0] == 1

    assert c.get("/api/clusters").json() == []
    with connect(tmp_path / "library") as conn:
        assert conn.execute("SELECT COUNT(*) FROM clusters WHERE name=?", (old_name,)).fetchone()[0] == 0
        assert conn.execute("SELECT cluster_id FROM items WHERE id=?", (created["id"],)).fetchone()["cluster_id"] is None


def test_create_simplified_prompt_adds_traditional_prompt(tmp_path):
    c = client(tmp_path)
    created = c.post("/api/items", json=create_payload(prompts=[{"language": "zh_hans", "text": "红龙云图"}])).json()
    prompts = {p["language"]: p["text"] for p in created["prompts"]}
    assert prompts["zh_hans"] == "红龙云图"
    assert prompts["zh_hant"] == "紅龍雲圖"
    assert c.get("/api/items", params={"q": "紅龍雲圖"}).json()["total"] == 1
