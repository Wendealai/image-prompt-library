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


def test_demo_bundle_preserves_xiaoxiaodong_qr_visual_design_prompt_safely():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050758676181622946-qr-code-visual-design" in items_text
    assert "GPT2: 二维码美化 x 设计感趣味感 x 搞自媒体、搞广告、学生党都笑了" in items_text
    assert "二维码是功能核心，必须保持可扫描" in items_text
    assert "用户最后输入的主题、文案或风格要求是" in items_text
    assert "deliberately non-scannable neutral preview" in items_text
    assert "demo-data/media/img_f54b86630dde7773.webp" in items_text
    assert (demo_root / "media" / "img_f54b86630dde7773.webp").exists()


def test_demo_bundle_preserves_vigo_sports_neon_type_poster_formula():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-vigocreativeai-2050822964975984748-sports-wide-angle-neon-type-poster" in items_text
    assert "真实运动广角荧光巨字广告海报模板" in items_text
    assert "real sports photography" in items_text
    assert "extreme close-distance wide-angle perspective" in items_text
    assert "giant fluorescent yellow typography" in items_text
    assert "Derived reusable template from the linked X status" in items_text
    assert "demo-data/media/img_7ee681d49678d0bb.webp" in items_text
    assert "demo-data/media/img_621d74ddc919bfff.webp" in items_text
    assert "demo-data/media/img_6a48a44df6dfe2e7.webp" in items_text
    assert "demo-data/media/img_8262292bf52c7499.webp" in items_text
    assert (demo_root / "media" / "img_7ee681d49678d0bb.webp").exists()
    assert (demo_root / "media" / "img_621d74ddc919bfff.webp").exists()
    assert (demo_root / "media" / "img_6a48a44df6dfe2e7.webp").exists()
    assert (demo_root / "media" / "img_8262292bf52c7499.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_lookalike_analysis_prompt_pair():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050809482461225398-dog-breed-lookalike-analysis-card" in items_text
    assert "x-xiaoxiaodong01-2050809482461225398-species-lookalike-analysis-card" in items_text
    assert "人像像什么狗狗品种分析对照图" in items_text
    assert "人像像什么生物物种分析对照图" in items_text
    assert "人像 vs 狗狗品种推测" in items_text
    assert "人像 vs 生物物种推测" in items_text
    assert "This item preserves the article's dog-breed version prompt" in items_text
    assert "This item preserves the article's all-species version prompt" in items_text
    assert "demo-data/media/img_342634c9c87a1954.webp" in items_text
    assert "demo-data/media/img_e1e2fc406182f49d.webp" in items_text
    assert (demo_root / "media" / "img_342634c9c87a1954.webp").exists()
    assert (demo_root / "media" / "img_e1e2fc406182f49d.webp").exists()


def test_demo_bundle_preserves_aleena_minimalist_country_sticker_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-aleenaamiir-2050591425746890778-minimalist-countries-sticker-collection" in items_text
    assert "Minimalist countries sticker collection" in items_text
    assert "Generate a minimalist sticker collection inspired by [COUNTRY]" in items_text
    assert "key landmarks, famous dishes, and cultural icons" in items_text
    assert "[COUNTY] is normalized to [COUNTRY]" in items_text
    assert "demo-data/media/img_22df2179556dad5a.webp" in items_text
    assert "demo-data/media/img_f62076d6e49da99a.webp" in items_text
    assert "demo-data/media/img_0d9e7d9f7420ad8a.webp" in items_text
    assert "demo-data/media/img_bdac07390924469a.webp" in items_text
    assert (demo_root / "media" / "img_22df2179556dad5a.webp").exists()
    assert (demo_root / "media" / "img_f62076d6e49da99a.webp").exists()
    assert (demo_root / "media" / "img_0d9e7d9f7420ad8a.webp").exists()
    assert (demo_root / "media" / "img_bdac07390924469a.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_professional_hr_headshot_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050604419562266917-professional-hr-headshot-template" in items_text
    assert "HR视角行业定制专业职业头像模板" in items_text
    assert "生成一张基于输入照片的专业职业头像" in items_text
    assert "符合专业HR审美" in items_text
    assert "适用于 腾讯 / MCN 部门" in items_text
    assert "the source/reference frame is not used as the primary demo image" in items_text
    assert "demo-data/media/img_3addccfc4a94041e.webp" in items_text
    assert "demo-data/media/img_b9b59871578a6c3b.webp" in items_text
    assert "demo-data/media/img_f3fa3b48c99b2c04.webp" in items_text
    assert "demo-data/media/img_880763843448fc1c.webp" in items_text
    assert (demo_root / "media" / "img_3addccfc4a94041e.webp").exists()
    assert (demo_root / "media" / "img_b9b59871578a6c3b.webp").exists()
    assert (demo_root / "media" / "img_f3fa3b48c99b2c04.webp").exists()
    assert (demo_root / "media" / "img_880763843448fc1c.webp").exists()


def test_demo_bundle_preserves_liyue_signature_selection_poster_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-liyue-ai-2050590199902790102-six-style-signature-selection-poster" in items_text
    assert "六款东方书法个人签名风格选择海报" in items_text
    assert "设计一张 9:16 竖版东方书法签名推荐海报" in items_text
    assert "生成 6 种不同但都适配该姓名的签名风格" in items_text
    assert "Prompt recovered from a search-indexed gptimg2.best prompt detail" in items_text
    assert "fxtwitter/vxtwitter exposed the main post and media but not the comment thread" in items_text
    assert "demo-data/media/img_1e952f35f6aaa9f1.webp" in items_text
    assert "demo-data/media/img_2be7674bb48f5178.webp" in items_text
    assert (demo_root / "media" / "img_1e952f35f6aaa9f1.webp").exists()
    assert (demo_root / "media" / "img_2be7674bb48f5178.webp").exists()


def test_demo_bundle_preserves_techiesa_body_part_infographic_template():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-techiebysa-2050582644031631861-body-part-technical-infographic-template" in items_text
    assert "Body part technical anatomy infographic template" in items_text
    assert "Create a detailed technical infographic image of" in items_text
    assert "photoreal render with precise blueprint-style educational annotations" in items_text
    assert "Derived reusable body-part variant from the linked X status" in items_text
    assert "current result image shows the same technical infographic formula applied to body parts" in items_text
    assert "demo-data/media/img_8653e9e65ea86b1b.webp" in items_text
    assert (demo_root / "media" / "img_8653e9e65ea86b1b.webp").exists()


def test_demo_bundle_preserves_xiaoxiaodong_how_to_infographic_card_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-xiaoxiaodong01-2050567345010307280-how-to-infographic-card-poster" in items_text
    assert "如何做信息图卡片海报设计提示词" in items_text
    assert "生成一张“如何做（How-to）信息图设计稿”" in items_text
    assert "用“视觉路径”表达过程，而不是列步骤" in items_text
    assert "如何说话滴水不漏" in items_text
    assert "Article title: GPT2: 百科海报 x 教程变卡片 x 清晰易懂 x 卡片设计 x 小红书号主 狂喜！" in items_text
    assert "demo-data/media/img_60a9abe353a8f28c.webp" in items_text
    assert "demo-data/media/img_4b2c739c712255f8.webp" in items_text
    assert (demo_root / "media" / "img_60a9abe353a8f28c.webp").exists()
    assert (demo_root / "media" / "img_4b2c739c712255f8.webp").exists()


def test_demo_bundle_preserves_geekcatx_travel_map_style_library_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-geekcatx-2050770412108456141-fun-travel-map-poster-style-library" in items_text
    assert "趣味旅行地图海报四风格提示词" in items_text
    assert "你是一位世界顶级的旅行主题地图插画师" in items_text
    assert "风格A｜温暖童趣风" in items_text
    assert "风格D｜水墨国风风" in items_text
    assert "目标城市：北京" in items_text
    assert "Prompt preserved from the linked X Note Tweet" in items_text
    assert "demo-data/media/img_7ba9dfa3c7779ee4.webp" in items_text
    assert "demo-data/media/img_ffb8fbf3505435d9.webp" in items_text
    assert "demo-data/media/img_8bb4e9290149dacc.webp" in items_text
    assert "demo-data/media/img_3fe16f4af24c6fe7.webp" in items_text
    assert (demo_root / "media" / "img_7ba9dfa3c7779ee4.webp").exists()
    assert (demo_root / "media" / "img_ffb8fbf3505435d9.webp").exists()
    assert (demo_root / "media" / "img_8bb4e9290149dacc.webp").exists()
    assert (demo_root / "media" / "img_3fe16f4af24c6fe7.webp").exists()


def test_demo_bundle_preserves_noor_creature_natural_history_infographic_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-noorwithwifi-2050532829977887073-creature-natural-history-infographic" in items_text
    assert "Creature natural-history encyclopedia infographic prompt" in items_text
    assert "A detailed scientific educational infographic about [Insert Creature" in items_text
    assert "3D skeletal structure, a skull anatomy diagram with labels" in items_text
    assert "Hunting Strategy" in items_text
    assert "Prompt preserved verbatim from the linked X Note Tweet" in items_text
    assert "demo-data/media/img_eb9d904cccef2508.webp" in items_text
    assert "demo-data/media/img_ab79b6cff4633658.webp" in items_text
    assert (demo_root / "media" / "img_eb9d904cccef2508.webp").exists()
    assert (demo_root / "media" / "img_ab79b6cff4633658.webp").exists()


def test_demo_bundle_preserves_charaspower_logo_ice_cube_product_photo_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-charaspowerai-2050613805227331745-logo-ice-cube-product-photo" in items_text
    assert "Logo ice cube macro product photography prompt" in items_text
    assert "ice cube sculpted in the shape of [brand] logo" in items_text
    assert "transparency, internal cracks, air bubbles, light refraction" in items_text
    assert "Banana Pro / Leonardo AI prompt" in items_text
    assert "demo-data/media/img_65130982210562e9.webp" in items_text
    assert "demo-data/media/img_a6d444ad8ec8a4da.webp" in items_text
    assert "demo-data/media/img_24c7bc72d06e6e24.webp" in items_text
    assert "demo-data/media/img_deb3c39512689916.webp" in items_text
    assert (demo_root / "media" / "img_65130982210562e9.webp").exists()
    assert (demo_root / "media" / "img_a6d444ad8ec8a4da.webp").exists()
    assert (demo_root / "media" / "img_24c7bc72d06e6e24.webp").exists()
    assert (demo_root / "media" / "img_deb3c39512689916.webp").exists()


def test_demo_bundle_preserves_azed_plush_pop_3d_render_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-azed-ai-2050878302827708548-plush-pop-3d-render" in items_text
    assert "Plush pop cute 3D collectible render prompt" in items_text
    assert "A soft plush 3D model of a [subject] with [key detail]" in items_text
    assert "velvety surface, squeezable toy-like form" in items_text
    assert "adorable collectible feel" in items_text
    assert "Prompt preserved verbatim from the linked X Note Tweet" in items_text
    assert "demo-data/media/img_6e40f7cbb8dfc000.webp" in items_text
    assert "demo-data/media/img_d6843715636a52c9.webp" in items_text
    assert "demo-data/media/img_77c73b524728d0d6.webp" in items_text
    assert "demo-data/media/img_7ef1f90207dd10ef.webp" in items_text
    assert (demo_root / "media" / "img_6e40f7cbb8dfc000.webp").exists()
    assert (demo_root / "media" / "img_d6843715636a52c9.webp").exists()
    assert (demo_root / "media" / "img_77c73b524728d0d6.webp").exists()
    assert (demo_root / "media" / "img_7ef1f90207dd10ef.webp").exists()


def test_demo_bundle_preserves_techiesa_anime_legends_poster_template():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-techiebysa-2050629331827703965-anime-legends-poster-template" in items_text
    assert "Anime legends 3D animated ensemble poster template" in items_text
    assert "The subject is [ANIME TITLE]" in items_text
    assert "Automatically select the most iconic and recognizable characters" in items_text
    assert "Derived reusable anime-poster variant from the linked X status" in items_text
    assert "public mirrors did not expose that comment" in items_text
    assert "Attack on Titan, Dragon Ball Z, One Piece, Naruto" in items_text
    assert "demo-data/media/img_7cc52cdc31298576.webp" in items_text
    assert (demo_root / "media" / "img_7cc52cdc31298576.webp").exists()


def test_demo_bundle_preserves_diplomeme_house_construction_video_template():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-diplomeme-2050843651379744922-house-construction-video-from-blueprint" in items_text
    assert "House construction video from blueprint and land prompt" in items_text
    assert "Empty land (site view)" in items_text
    assert "Marking layout" in items_text
    assert "Final house exterior (complete build)" in items_text
    assert "Derived reusable construction-video template" in items_text
    assert "public mirrors did not expose the source prompt/comment" in items_text
    assert "demo-data/media/img_93044b1d3e2bc10d.webp" in items_text
    assert (demo_root / "media" / "img_93044b1d3e2bc10d.webp").exists()


def test_demo_bundle_preserves_lexnlin_ai_agency_website_section_prompt():
    demo_root = ROOT / "frontend" / "public" / "demo-data"
    items_text = (demo_root / "items.json").read_text()

    assert "x-lexnlin-2050709691978936715-ai-agency-website-section-images" in items_text
    assert "AI agency website section image set prompt" in items_text
    assert "generate images for a website for an AI agency" in items_text
    assert "one image per section, for a total of eight distinct images" in items_text
    assert "Awwwards SOTD-level website" in items_text
    assert "Do not combine them into one image" in items_text
    assert "Prompt preserved verbatim from the linked X Note Tweet" in items_text
    assert 'Quote tweet text: \\"Images 2.0 website. Takes one prompt.' in items_text
    assert "demo-data/media/img_94a435ae61efcc2c.webp" in items_text
    assert "demo-data/media/img_f5f85d1dc9fe399c.webp" in items_text
    assert "demo-data/media/img_a27c542f210674e5.webp" in items_text
    assert "demo-data/media/img_3955f239a55168cc.webp" in items_text
    assert (demo_root / "media" / "img_94a435ae61efcc2c.webp").exists()
    assert (demo_root / "media" / "img_f5f85d1dc9fe399c.webp").exists()
    assert (demo_root / "media" / "img_a27c542f210674e5.webp").exists()
    assert (demo_root / "media" / "img_3955f239a55168cc.webp").exists()
