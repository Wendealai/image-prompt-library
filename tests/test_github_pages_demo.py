import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_github_pages_demo_mode_uses_static_data_and_base_path():
    vite_config = (ROOT / "vite.config.ts").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    package_json = (ROOT / "package.json").read_text()

    assert "VITE_BASE_PATH" in vite_config
    assert "base:" in vite_config
    assert "VITE_DEMO_MODE" in client
    assert "VITE_DEMO_ASSET_VERSION" in client
    assert "DEMO_DATA_BASE" in client
    assert "demo-data/items.json" in client
    assert "demo-data/clusters.json" in client
    assert "demo-data/tags.json" in client
    assert "mediaUrl = (path?: string)" in client
    assert "demoUrl" in client
    assert '"build:demo"' in package_json
    assert "VITE_DEMO_MODE=true" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/" in package_json


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
    assert "MOBILE_PREVIEW_PATH: v0.2" in text
    assert "VITE_DEMO_ASSET_VERSION=${GITHUB_SHA}" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${MOBILE_PREVIEW_PATH}/ npm run build" in text
    assert "git worktree add .page-build/${LEGACY_DEMO_PATH} ${LEGACY_DEMO_REF}" in text
    assert "VITE_BASE_PATH=/image-prompt-library/${LEGACY_DEMO_PATH}/ npm run build" in text
    assert ".pages-artifact/${MOBILE_PREVIEW_PATH}" in text
    assert ".pages-artifact/${LEGACY_DEMO_PATH}" in text
    assert "Choose a preview" in text
    assert "Mobile browsing preview" in text
    assert "Original alpha demo" in text
    assert "path: .pages-artifact" in text


def test_package_exposes_versioned_demo_build_scripts():
    package_json = (ROOT / "package.json").read_text()
    assert '"build:demo:v0.1"' in package_json
    assert '"build:demo:v0.2"' in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.1/" in package_json
    assert "VITE_BASE_PATH=/image-prompt-library/v0.2/" in package_json


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


def test_demo_bundle_preserves_curated_aijaz_avatar_prompt_imports():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-iamsofiaijaz-2049895027560866232" in items_text
    assert "x-iamsofiaijaz-2049895027560866232-formula" in items_text
    assert "Prompt reconstructed from a truncated X post by Aijaz" in items_text
    assert "Derived reusable template based on the linked X post by Aijaz" in items_text
    assert "This item now reuses the source post's example image" in items_text
    assert "demo-data/media/img_1e6efab8a3954dc9.webp" in items_text
    assert "demo-data/media/img_d08c050833bc4a77.webp" in items_text
    assert (demo_root / "media" / "img_1e6efab8a3954dc9.webp").exists()
    assert (demo_root / "media" / "img_d08c050833bc4a77.webp").exists()


def test_demo_bundle_preserves_safety_curated_specimen_card_preview():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-iqrasaifiii-2049790084220928090" in items_text
    assert "安全样张证件道具近景摄影" in items_text
    assert "source post's clearly fictional sample output image" in items_text
    assert "demo-data/media/img_525f8d4c7fd74df0.webp" in items_text
    assert (demo_root / "media" / "img_525f8d4c7fd74df0.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_article_lego_prompt_pair():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050041783053439332-lego-poster-complex" in items_text
    assert "x-xiaoxiaodong01-2050041783053439332-lego-poster-minimal" in items_text
    assert "GPT2实战： 乐高 x 文字 x 无限可能" in items_text
    assert "This item preserves the article's 复杂版本 prompt" in items_text
    assert "This item preserves the article's 极简版本 prompt" in items_text
    assert "demo-data/media/img_6e2d4bb9d4f74d30.webp" in items_text
    assert (demo_root / "media" / "img_6e2d4bb9d4f74d30.webp").exists()


def test_demo_bundle_preserves_op7418_photo_annotation_core_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-op7418-2050079838179135746-photo-annotation-core" in items_text
    assert "手绘风照片物件注解简洁版" in items_text
    assert "This item therefore attributes 歸藏(guizang.ai) (@op7418) as the sharer rather than the original author." in items_text
    assert "demo-data/media/img_4c6d65dd2ccb4d2e.webp" in items_text
    assert (demo_root / "media" / "img_4c6d65dd2ccb4d2e.webp").exists()


def test_demo_bundle_preserves_qisi_3x4_minimal_portrait_poster_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-qisi-ai-2050079074257957008-3x4-minimal-portrait-poster" in items_text
    assert "3:4高级极简人像海报提示词" in items_text
    assert "this status publishes a distinct 3:4 advanced minimalist portrait-poster variant." in items_text
    assert "demo-data/media/img_4f7a97637f1d4517.webp" in items_text
    assert (demo_root / "media" / "img_4f7a97637f1d4517.webp").exists()


def test_demo_bundle_preserves_ciri_gym_chibi_scrapbook_edit():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-ciri-ai-2050094437821513896-gym-chibi-scrapbook-edit" in items_text
    assert "Gym photo chibi scrapbook edit" in items_text
    assert "adding chibi mini-characters, doodles, and handwritten motivational phrases." in items_text
    assert "demo-data/media/img_8b0034ea319e7aac.webp" in items_text
    assert "demo-data/media/img_7994f52570a7b8d1.webp" in items_text
    assert (demo_root / "media" / "img_8b0034ea319e7aac.webp").exists()
    assert (demo_root / "media" / "img_7994f52570a7b8d1.webp").exists()


def test_demo_bundle_preserves_web3annie_scribbli_redraw_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-web3annie-2050110913295122804-scribbli-redraw" in items_text
    assert "Scribbli 潦草风重绘提示词" in items_text
    assert "currently popular Scribbli rough-doodle redraw style." in items_text
    assert "demo-data/media/img_65929da82f6521b5.webp" in items_text
    assert "demo-data/media/img_3a78a909442e1590.webp" in items_text
    assert (demo_root / "media" / "img_65929da82f6521b5.webp").exists()
    assert (demo_root / "media" / "img_3a78a909442e1590.webp").exists()


def test_demo_bundle_preserves_mrlarus_posture_analysis_report_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-mrlarus-2050074075016384834-posture-analysis-report" in items_text
    assert "AI体态比例管理报告提示词" in items_text
    assert "https://x.com/MrLarus/status/2050074225914835401" in items_text
    assert "demo-data/media/img_cb56452ed0cb5ea8.webp" in items_text
    assert "demo-data/media/img_100e30860abd7943.webp" in items_text
    assert (demo_root / "media" / "img_cb56452ed0cb5ea8.webp").exists()
    assert (demo_root / "media" / "img_100e30860abd7943.webp").exists()


def test_demo_bundle_preserves_zahra_mini_me_emotional_composite_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-zahra4sure-2049852941969072517-mini-me-emotional-composite" in items_text
    assert "Mini-me emotional composite around portrait" in items_text
    assert "The post explicitly says the example was created on Gemini Nano Banana." in items_text
    assert "demo-data/media/img_39eec3a66fe24de1.webp" in items_text
    assert (demo_root / "media" / "img_39eec3a66fe24de1.webp").exists()


def test_demo_bundle_preserves_lucy_old_photo_restoration_prompt_excerpt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-lucy-love-ai-2050130365625638985-old-photo-4k-restoration" in items_text
    assert "老照片 4K 修复提示词（缩略版）" in items_text
    assert "this item preserves that abbreviated source text verbatim rather than reconstructing missing instructions." in items_text
    assert "https://x.com/Lucy_love_AI/status/2050130367378841724" in items_text
    assert "demo-data/media/img_127c532457ab7bfc.webp" in items_text
    assert "demo-data/media/img_785e0c3e2d000c8f.webp" in items_text
    assert (demo_root / "media" / "img_127c532457ab7bfc.webp").exists()
    assert (demo_root / "media" / "img_785e0c3e2d000c8f.webp").exists()


def test_demo_bundle_preserves_gdgtify_survival_gear_design_board_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-gdgtify-2050131863218577683-survival-gear-design-board" in items_text
    assert "Survival-grade everyday product design board" in items_text
    assert "ordinary products into survival-grade concepts through a 2x2 technical design-board structure." in items_text
    assert "demo-data/media/img_f8b463a814766b62.webp" in items_text
    assert (demo_root / "media" / "img_f8b463a814766b62.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_logo_grid_article_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050152425395519966-logo-grid-prompt" in items_text
    assert "饭店 logo 创意 4x4 网格提示词" in items_text
    assert "Article title: GPT2: 人人都是logo设计师...此话当真！" in items_text
    assert "强记粉店" in items_text
    assert "demo-data/media/img_7082bbd31647bd6c.webp" in items_text
    assert (demo_root / "media" / "img_7082bbd31647bd6c.webp").exists()


def test_demo_bundle_preserves_zahra_editorial_portrait_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-zahra4sure-2050015163219378680-editorial-portrait-painting" in items_text
    assert "Editorial portrait with abstract self-portrait backdrop" in items_text
    assert "created on Gemini Nano Banana" in items_text
    assert "including its source typos and gendered wording inconsistencies" in items_text
    assert "demo-data/media/img_02f3be8e77a76f56.webp" in items_text
    assert (demo_root / "media" / "img_02f3be8e77a76f56.webp").exists()


def test_demo_bundle_preserves_mrgafish_outfit_transfer_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-mrgafish-2049793669755183413-outfit-transfer" in items_text
    assert "参考服装拆解换装提示词" in items_text
    assert "using image 1 as the outfit reference and image 2 as the target person." in items_text
    assert "demo-data/media/img_f404303559f2e25a.webp" in items_text
    assert "demo-data/media/img_6ef85d7565cf34f5.webp" in items_text
    assert (demo_root / "media" / "img_f404303559f2e25a.webp").exists()
    assert (demo_root / "media" / "img_6ef85d7565cf34f5.webp").exists()


def test_demo_bundle_preserves_leyu_dragon_ball_editorial_cover_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-leyu37829-2049814392330682700-dragon-ball-editorial-cover" in items_text
    assert "七龙珠高定封面角色海报通用模板" in items_text
    assert "only the core character name needs to be replaced" in items_text
    assert "Cell (Perfect Form・Full Power) – Dragon Ball Z / Android Saga." in items_text
    assert "demo-data/media/img_311d261a0d197b5a.webp" in items_text
    assert "demo-data/media/img_e4ccfc18ea577a6d.webp" in items_text
    assert "demo-data/media/img_bbbeaf4e81ef776c.webp" in items_text
    assert "demo-data/media/img_8c6151c65d4ba038.webp" in items_text
    assert (demo_root / "media" / "img_311d261a0d197b5a.webp").exists()
    assert (demo_root / "media" / "img_e4ccfc18ea577a6d.webp").exists()
    assert (demo_root / "media" / "img_bbbeaf4e81ef776c.webp").exists()
    assert (demo_root / "media" / "img_8c6151c65d4ba038.webp").exists()


def test_demo_bundle_preserves_olivio_granny_game_concept_sheet():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-oliviosarikas-2049939963022913651-granny-game-concept-sheet" in items_text
    assert "3x2 AAA granny demon-hunter game concept sheet" in items_text
    assert "preserves that source text verbatim rather than inferring omitted continuation" in items_text
    assert "https://x.com/OlivioSarikas/status/2049939967422644463" in items_text
    assert "demo-data/media/img_35458b89906cc8d4.webp" in items_text
    assert "demo-data/media/img_09d676df6c8ccb24.webp" in items_text
    assert "demo-data/media/img_5b77bc6c5a6d16be.webp" in items_text
    assert (demo_root / "media" / "img_35458b89906cc8d4.webp").exists()
    assert (demo_root / "media" / "img_09d676df6c8ccb24.webp").exists()
    assert (demo_root / "media" / "img_5b77bc6c5a6d16be.webp").exists()


def test_demo_bundle_preserves_noor_burning_social_profile_portrait():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-noor-ul-ain43-2050005353392423033-burning-social-profile-portrait" in items_text
    assert "Burning social profile portrait prompt" in items_text
    assert "partially burning printed social-media profile page" in items_text
    assert "username “Noor 🌸” and bio text, девушка" in items_text
    assert "demo-data/media/img_6715ea2b31f6158a.webp" in items_text
    assert (demo_root / "media" / "img_6715ea2b31f6158a.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_miniature_building_prompt_pair():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050178967362302215-miniature-building-poster-soft" in items_text
    assert "x-xiaoxiaodong01-2050178967362302215-miniature-building-poster-vivid" in items_text
    assert "微缩模型等距建筑海报柔和文字版" in items_text
    assert "微缩模型等距建筑海报鲜明无字版" in items_text
    assert "Article title: GPT2: 微缩模型 x 万物可转 x 提示词 x 有韦斯安德森的味道。" in items_text
    assert 'sample theme \\"星巴克咖啡\\"' in items_text
    assert 'sample theme \\"茶饮悦色\\"' in items_text
    assert "demo-data/media/img_0eb6f8a452028fba.webp" in items_text
    assert (demo_root / "media" / "img_0eb6f8a452028fba.webp").exists()


def test_demo_bundle_preserves_rovvmut_north_face_brand_poster():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-rovvmut-2050168053523157062-north-face-brand-concept-poster" in items_text
    assert "The North Face cinematic brand concept poster" in items_text
    assert "made with GPT Image 2 on ChatGPT" in items_text
    assert 'A high-fashion, cinematic brand concept poster for \\"The North Face.\\"' in items_text
    assert "demo-data/media/img_06f766130ada4daa.webp" in items_text
    assert (demo_root / "media" / "img_06f766130ada4daa.webp").exists()


def test_demo_bundle_preserves_lariab_google_search_profile_ui():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-aiwithlariab-2050174040732738004-google-search-profile-ui" in items_text
    assert "Google search profile UI portrait prompt" in items_text
    assert "made on Gemini Nano banana 2" in items_text
    assert "Name: Lariab ✔️" in items_text
    assert "Champion of “kal se pakka”" in items_text
    assert "demo-data/media/img_215e9418e73f7ad3.webp" in items_text
    assert (demo_root / "media" / "img_215e9418e73f7ad3.webp").exists()


def test_demo_bundle_preserves_diplomeme_superdry_branding_grid():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-diplomeme-2050184712195588291-superdry-branding-grid" in items_text
    assert "Superdry modular branding grid prompt" in items_text
    assert "Prompt extracted from the author self-reply" in items_text
    assert "premium editorial Superdry identity board" in items_text
    assert "https://x.com/Diplomeme/status/2050184971621716192" in items_text
    assert "demo-data/media/img_97cc291f3019535a.webp" in items_text
    assert (demo_root / "media" / "img_97cc291f3019535a.webp").exists()


def test_demo_bundle_preserves_shushant_whiteboard_animation_portrait():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-shushant-l-2050183637195522456-whiteboard-animation-portrait" in items_text
    assert "Whiteboard animation style portrait from reference image" in items_text
    assert "Google Nano Banana Pro" in items_text
    assert "clean whiteboard animation style illustration of the person from the reference image" in items_text
    assert "demo-data/media/img_da059d440a6cb4fb.webp" in items_text
    assert "demo-data/media/img_381cc9a3fba59bb0.webp" in items_text
    assert "demo-data/media/img_df38246de6dfacd8.webp" in items_text
    assert "demo-data/media/img_2437873add412bc4.webp" in items_text
    assert (demo_root / "media" / "img_da059d440a6cb4fb.webp").exists()
    assert (demo_root / "media" / "img_381cc9a3fba59bb0.webp").exists()
    assert (demo_root / "media" / "img_df38246de6dfacd8.webp").exists()
    assert (demo_root / "media" / "img_2437873add412bc4.webp").exists()


def test_demo_bundle_preserves_zephyra_epic_film_frame_formula():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-zephyraleigh-2049916220179374125-epic-film-frame-illustration-formula" in items_text
    assert "Epic film-frame illustration formula prompt" in items_text
    assert "reusable formula prompt for creating epic film-like illustrated frames" in items_text
    assert "demo-data/media/img_13a29a6ddd9a4bbf.webp" in items_text
    assert "demo-data/media/img_e268fbfc55a344a1.webp" in items_text
    assert (demo_root / "media" / "img_13a29a6ddd9a4bbf.webp").exists()
    assert (demo_root / "media" / "img_e268fbfc55a344a1.webp").exists()


def test_demo_bundle_preserves_samia_crayon_profile_redraw():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-oye-samia-2050130847991488815-crayon-profile-screenshot-redraw" in items_text
    assert "Cute crayon-style profile screenshot redraw" in items_text
    assert "made with Gemini Nano Banana" in items_text
    assert "Upload a screenshot of your profile" in items_text
    assert "full of childlike innocence" in items_text
    assert "demo-data/media/img_7507e546a0624c2d.webp" in items_text
    assert (demo_root / "media" / "img_7507e546a0624c2d.webp").exists()
