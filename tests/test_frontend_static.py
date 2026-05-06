from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compact(text: str) -> str:
    return "".join(text.split())


def test_item_save_refreshes_visible_item_query():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    assert "const [itemsReloadKey, setItemsReloadKey]" in app
    assert "useItemsQuery(debouncedQ, clusterId, undefined, 1000, itemsReloadKey)" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "reloadKey" in hook
    assert "[q, clusterId, tag, viewLimit, reloadKey]" in hook


def test_topbar_is_toolbar_search_not_hero_or_keyboard_shortcut():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    assert "toolbar-search" in topbar
    assert "active-filter-strip" in topbar
    assert "view-dock" in topbar
    assert "hero-shell" not in topbar
    assert "Start your visual prompt collection" not in topbar
    assert "Keyboard shortcut" not in topbar
    assert "⌘K" not in topbar and "Ctrl+K" not in topbar
    assert "metaKey" not in app and "ctrlKey" not in app


def test_mobile_has_real_viewport_meta_for_iphone_breakpoints():
    index = (ROOT / "frontend" / "index.html").read_text()
    assert 'name="viewport"' in index
    assert "width=device-width" in index
    assert "initial-scale=1" in index


def test_mobile_defaults_to_cards_without_stale_pre_mobile_saved_view():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    assert "VIEW_STORAGE_KEY = 'image-prompt-library.view_mode.v2'" in app
    assert "function loadPreferredView(): ViewMode" in app
    assert "window.localStorage.getItem(VIEW_STORAGE_KEY)" in app
    assert "window.matchMedia('(max-width: 760px)').matches" in app
    assert "return isMobileViewport ? 'cards' : 'explore'" in app
    assert "const [view, setView] = useState<ViewMode>(loadPreferredView)" in app
    assert "const updateView = (nextView: ViewMode) => {" in app
    assert "window.localStorage.setItem(VIEW_STORAGE_KEY, nextView)" in app
    assert "onView={updateView}" in app


def test_mobile_cards_use_touch_visible_two_column_masonry():
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "desktop-cards-grid" in cards
    assert "mobile-masonry-columns" in cards
    assert "mobile-masonry-column" in cards
    assert "leftColumnItems" in cards and "rightColumnItems" in cards
    assert "items.filter((_, index) => index % 2 === 0)" in cards
    assert "items.filter((_, index) => index % 2 === 1)" in cards
    assert "action-label" in card
    assert ".mobile-masonry-columns{display:none}" in compact_css
    assert ".desktop-cards-grid{display:block}" in compact_css
    assert ".desktop-cards-grid{display:none}" in compact_css
    assert ".mobile-masonry-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));" in compact_css
    assert "column-count:2" not in compact_css
    assert "grid-template-columns:repeat(3" not in compact_css
    assert ".mobile-masonry-columns.card-image-frame{min-height:0" in compact_css
    assert ".mobile-masonry-columns.card-image-frame.has-reserved-ratio{aspect-ratio:auto!important}" in compact_css
    assert ".mobile-masonry-columns.card-image-frameimg{width:100%;height:auto;object-fit:contain" in compact_css
    assert ".item-card.card-actions{opacity:1;transform:none;flex-direction:row;" in compact_css
    assert ".hover-action.action-label{display:none}" in compact_css


def test_card_display_uses_preview_or_original_before_thumbnail_for_adaptive_images():
    images = (ROOT / "frontend" / "src" / "utils" / "images.ts").read_text()
    assert "return image?.preview_path || image?.original_path || image?.thumb_path || ''" in images
    assert "export function imageDisplayPaths(image?: ImageRecord)" in images
    assert "uniquePaths([image?.preview_path, image?.original_path, image?.thumb_path])" in images
    assert "export function imageHeroPaths(image?: ImageRecord)" in images
    assert "export function imageThumbnailPaths(image?: ImageRecord)" in images


def test_frontend_images_have_load_failure_fallbacks():
    fallback = (ROOT / "frontend" / "src" / "components" / "FallbackImage.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "setPathIndex(currentIndex => Math.min(currentIndex + 1, imagePaths.length))" in fallback
    assert "src={mediaUrl(imagePaths[pathIndex])}" in fallback
    assert "fallback={<span className=\"placeholder image-load-fallback\">{t('noImage')}</span>}" in card
    assert "paths={imageHeroPaths(activeImage)}" in detail
    assert "paths={node.imagePaths}" in explore
    assert ".image-load-fallback" in css


def test_cards_are_global_image_overlay_cards():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "<h3>{item.title}</h3>" in card
    assert "item.cluster?.name" not in card
    assert "item.source_name" not in card
    assert "item.model" not in card
    assert ".item-card{position:relative;" in compact_css
    assert ".card-body{position:absolute;left:0;right:0;bottom:0;" in compact_css
    assert "linear-gradient(transparent,rgba(33,25,34,.82))" in compact_css
    assert ".card-bodyh3" in compact_css and "color:white" in compact_css
    assert ".card-bodyp" not in compact_css


def test_desktop_cards_are_wider_on_large_screens_for_seven_column_layout():
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "@media(min-width:1760px){:root{--card-min:260px}" in compact_css
    assert "max-width:1920px" in compact_css


def test_mobile_header_keeps_brand_centered_and_status_inline():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "mobile-brand" in topbar
    assert "mobile-status-view-row" in topbar
    assert topbar.index("filter-button") < topbar.index("toolbar-search") < topbar.index("mobile-brand") < topbar.index("config-button")
    assert "{count} {t('referencesShown')}" in topbar
    assert "references shown" not in (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    assert ".nav-row{display:grid;grid-template-columns:autominmax(340px,1fr)autoauto;" in compact_css
    assert ".logo{grid-column:1/-1;justify-self:center;order:-1}" not in compact_css
    assert ".nav-row{grid-template-columns:auto1frauto;" in compact_css
    assert ".toolbar-search{grid-column:1/-1;order:4}" in compact_css
    assert ".mobile-brand{justify-self:center" in compact_css
    assert ".status-row{flex-direction:row;align-items:center;" in compact_css


def test_mobile_selected_collection_uses_bottom_floating_dock_and_active_filter_state():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "selectedCollectionNameSizeClass" in app
    assert "selected-collection-dock" in app
    assert "selected-collection-name" in app
    assert "selected-collection-count" in app
    assert "is-long" in app and "is-very-long" in app
    assert "!filtersOpen && !configOpen && !detailId && !editorOpen" in app
    assert "hasActiveFilter" in topbar
    assert "filter-button" in topbar and "' active'" in topbar
    assert "filter-active-dot" not in topbar
    assert "filter-active-count" not in topbar
    assert ".filter-button.active" in css
    assert ".filter-active-dot" not in css
    assert ".filter-active-count" not in css
    assert "@media(max-width:760px)" in css
    assert ".active-filter-strip.active-filter{display:none}" in compact_css
    assert ".selected-collection-dock{position:fixed;left:16px;right:16px;bottom:calc(16px+env(safe-area-inset-bottom));" in compact_css
    assert ".selected-collection-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:clamp(14px,3.7vw,16px);" in compact_css
    assert ".selected-collection-name.is-long{font-size:clamp(12.5px,3.25vw,14.5px)}" in compact_css
    assert ".selected-collection-name.is-very-long{font-size:clamp(12px,3vw,13.5px)}" in compact_css
    assert "@media(max-width:380px){.selected-collection-count{display:none}}" in compact_css
    assert "main{padding:22px14px150px}" in compact_css


def test_mobile_detail_modal_has_image_first_floating_controls():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    compact_css = css.replace(" ", "")
    assert "mobile-hero-actions" in detail
    assert "mobile-hero-close" in detail
    assert "mobile-hero-primary-actions" in detail
    assert "const [imageViewerOpen, setImageViewerOpen] = useState(false);" in detail
    assert "const [imageViewerScale, setImageViewerScale] = useState(1);" in detail
    assert "const imageViewerScaleRef = useRef(1);" in detail
    assert "const imageViewerScrollRef = useRef<HTMLDivElement>(null);" in detail
    assert "const pinchGestureRef = useRef<{ distance: number; scale: number } | null>(null);" in detail
    assert "className=\"hero-image-button\"" in detail
    assert "className=\"detail-image-viewer\"" in detail
    assert "className=\"detail-image-viewer-controls\"" in detail
    assert "style={{ width: `${imageViewerScale * 100}%` }}" in detail
    assert "const IMAGE_VIEWER_DOUBLE_TAP_SCALE = 2.4;" in detail
    assert "function clampImageViewerScale(scale: number)" in detail
    assert "function measureTouchDistance(firstTouch: { clientX: number; clientY: number }, secondTouch: { clientX: number; clientY: number })" in detail
    assert "setImageViewerScale(scale => clampImageViewerScale(scale + delta));" in detail
    assert "onDoubleClick={event => toggleImageViewerZoom(event.clientX, event.clientY)}" in detail
    assert "onTouchStart={handleImageViewerTouchStart}" in detail
    assert "onTouchMove={handleImageViewerTouchMove}" in detail
    assert "aria-label={t('openImageDetailViewer')}" in detail
    assert "aria-label={item.favorite ? t('saved') : t('favorite')}" in detail
    assert "aria-label={t('edit')}" in detail
    assert ".detail.modal{width:100vw;max-height:100dvh;" in compact_css
    assert ".modal-hero{min-height:0;height:auto;" in compact_css
    assert ".hero-image-button{width:100%;height:100%;display:block;border:0;padding:0;background:transparent;cursor:zoom-in}" in compact_css
    assert ".hero-image{width:100%;height:auto;max-height:none;object-fit:contain}" in compact_css
    assert ".mobile-hero-actions{display:block}" in compact_css
    assert ".mobile-hero-close{position:absolute;right:12px;top:calc(12px+env(safe-area-inset-top));" in compact_css
    assert ".mobile-hero-primary-actions{position:absolute;right:12px;bottom:12px;" in compact_css
    assert ".detail-image-viewer{position:absolute;inset:0;z-index:16;" in compact_css
    assert ".detail-image-viewer-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap}" in compact_css
    assert ".detail-image-viewer-scroll{min-height:0;overflow:auto;" in compact_css
    assert "touch-action:manipulation" in css
    assert "-webkit-overflow-scrolling:touch" in css
    assert "| 'openImageDetailViewer' | 'imageDetailViewer' | 'imageDetailViewerHint'" in i18n
    assert "openImageDetailViewer: 'Open image detail viewer'" in i18n
    assert "imageDetailViewer: 'Image detail viewer'" in i18n
    assert "imageDetailViewerHint: 'Drag to inspect details, and use double-tap or pinch gestures to zoom in or out.'" in i18n


def test_detail_modal_does_not_call_hooks_after_empty_id_guard():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    guard_index = detail.index("if (!id) return null;")
    assert "useEffect(" not in detail[guard_index:]


def test_detail_modal_includes_ai_rewrite_panel_and_prompt_template_api_hooks():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    panel = (ROOT / "frontend" / "src" / "components" / "PromptTemplatePanel.tsx").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    prompt_template_utils = (ROOT / "frontend" / "src" / "utils" / "promptTemplate.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "PromptTemplatePanel" in detail
    assert "<PromptTemplatePanel" in detail
    assert "onImageGenerated={result => {" in detail
    assert "api.promptTemplate(itemId)" in panel
    assert "api.initPromptTemplate(itemId)" not in panel
    assert "api.generatePromptVariant(template.id, nextKeyword)" in panel
    assert "api.rerollPromptVariant(currentSession.id" in panel
    assert "buildSlotValueRecord" in panel
    assert "renderMarkedPrompt(template.marked_text, editorValues)" in panel
    assert "slotInputRefs = useRef<Record<string, HTMLTextAreaElement | null>>({})" in panel
    assert "const [draftBaseValues, setDraftBaseValues] = useState<Record<string, string>>({})" in panel
    assert "const applyDraftValues = useCallback((nextValues: Record<string, string>, nextVariantId: string) => {" in panel
    assert "targetedSlotId" in panel
    assert "handleJumpToSlot" in panel
    assert "handleApplyVariantChanges" in panel
    assert "promptTemplateReplaceAllSlots" in panel
    assert "promptTemplateVariantReadyDraftPreserved" in panel
    assert "promptTemplateManualEdits" in panel
    assert "manualEditedSlotCount" in panel
    assert "applyImpactCount" in panel
    assert "replaceImpactCount" in panel
    assert "setEditorValues(current => ({ ...current, [slotId]: text }))" in panel
    assert "variant.segments" in panel
    assert "promptTemplateAppliedChangedSlots" in panel
    assert "promptTemplateApplyChangedSlots" in panel
    assert "setFeedback({ tone: 'success', message: t('promptTemplateVariantReadyDraftPreserved') })" in panel
    assert "}, [template?.id, template?.updated_at, loadEditorDraft]);" in panel
    assert "latestVariant?.id, loadEditorDraft" not in panel
    assert "target.scrollIntoView({ block: 'center', behavior: 'smooth' })" in panel
    assert "target.focus({ preventScroll: true })" in panel
    assert "prompt-remix-segment-button" in panel
    assert "renderPreviewSegment(segment, `assembled-${index}`)" in panel
    assert "prompt-remix-editor" in panel
    assert "prompt-remix-original" in panel
    assert "promptTemplateSlotEditor" in panel
    assert "promptTemplateAssemble" in panel
    assert "promptTemplateCopyFinal" in panel
    assert "handleGenerateImage" in panel
    assert "imageGenerationState" in panel
    assert "IMAGE_GENERATION_STAGE_DELAY_MS = 2200" in panel
    assert "prompt-remix-image-config" in panel
    assert "promptTemplateImageSettings" in panel
    assert "promptTemplateImageAspectRatio" in panel
    assert "promptTemplateImageResolution" in panel
    assert "promptTemplateImageStyle" in panel
    assert "promptTemplateImageCount" in panel
    assert "promptTemplateImageStrength" in panel
    assert "promptTemplateImageQueued" in panel
    assert "promptTemplateImageRendering" in panel
    assert "promptTemplateImageRetry" in panel
    assert "promptTemplateImageFocused" in panel
    assert "IMAGE_GENERATION_PRESETS_STORAGE_KEY = 'image-prompt-library.image_generation_presets.v1'" in panel
    assert "IMAGE_GENERATION_RECENT_OPTIONS_STORAGE_KEY = 'image-prompt-library.image_generation_recent_options.v1'" in panel
    assert "prompt-remix-preset-section" in panel
    assert "savedImagePresets" in panel
    assert "recentImageGenerationOptions" in panel
    assert "handleSaveImagePreset" in panel
    assert "handleDeleteImagePreset" in panel
    assert "handleApplyImagePreset" in panel
    assert "buildImageReferenceInputs" in panel
    assert "prompt-remix-reference-section" in panel
    assert "referenceImages={uniqueImages}" in detail
    assert "promptTemplateImagePresets" in panel
    assert "promptTemplateImagePresetDefault" in panel
    assert "promptTemplateImagePresetRecent" in panel
    assert "promptTemplateImagePresetNamePlaceholder" in panel
    assert "promptTemplateImagePresetSave" in panel
    assert "promptTemplateImagePresetSaved" in panel
    assert "promptTemplateImagePresetDelete" in panel
    assert "promptTemplateImagePresetNameRequired" in panel
    assert "api.generateImageFromPrompt(itemId, promptText, imageGenerationOptions, references)" in panel
    assert "promptTemplateGenerateImage" in panel
    assert "promptTemplateGenerateImageToImage" in panel
    assert "promptTemplateGeneratingImage" in panel
    assert "api.acceptPromptVariant(variant.id)" not in panel
    assert "promptTemplate: (itemId: string)" in client
    assert "adminInitPromptTemplate: (itemId: string, language?: string)" in client
    assert "adminPromptTemplate: (itemId: string)" in client
    assert "generatePromptVariant: (templateId: string, themeKeyword: string" in client
    assert "rerollPromptVariant: (sessionId: string" in client
    assert "acceptPromptVariant: (variantId: string)" in client
    assert "generateImageFromPrompt: (itemId: string, prompt: string, generation?: PromptImageGenerationOptions, references: PromptImageReferenceInput[] = [])" in client
    assert "| 'aiRewrite' | 'aiRewriteHelp'" in i18n
    assert "promptTemplateSlotEditor" in i18n
    assert "promptTemplateReplaceAllSlots" in i18n
    assert "promptTemplateApplyChangedSlots" in i18n
    assert "promptTemplateAppliedChangedSlots" in i18n
    assert "promptTemplateVariantReadyDraftPreserved" in i18n
    assert "promptTemplateManualEdits" in i18n
    assert "promptTemplateAssemble" in i18n
    assert "promptTemplateCopyFinal" in i18n
    assert "promptTemplateGenerateImage" in i18n
    assert "promptTemplateDirectImageHelp" in i18n
    assert "promptTemplateGeneratingImage" in i18n
    assert "promptTemplateImageSettings" in i18n
    assert "promptTemplateImageSettingsHelp" in i18n
    assert "promptTemplateImageResolution" in i18n
    assert "promptTemplateImageAspectRatio" in i18n
    assert "promptTemplateImageStyle" in i18n
    assert "promptTemplateImageCount" in i18n
    assert "promptTemplateImageStrength" in i18n
    assert "promptTemplateImageQueued" in i18n
    assert "promptTemplateImageRendering" in i18n
    assert "promptTemplateImageRetry" in i18n
    assert "promptTemplateImageFocused" in i18n
    assert "promptTemplateImagePresets" in i18n
    assert "promptTemplateImagePresetsHelp" in i18n
    assert "promptTemplateImagePresetDefault" in i18n
    assert "promptTemplateImagePresetRecent" in i18n
    assert "promptTemplateImagePresetNamePlaceholder" in i18n
    assert "promptTemplateImagePresetSave" in i18n
    assert "promptTemplateImagePresetSaved" in i18n
    assert "promptTemplateImagePresetDelete" in i18n
    assert "promptTemplateImagePresetNameRequired" in i18n
    assert "promptTemplateImageReferences" in i18n
    assert "promptTemplateImageToImageMode" in i18n
    assert ".prompt-remix-preset-section{display:flex;flex-direction:column;" in compact_css
    assert ".prompt-remix-preset-chip{display:inline-flex;align-items:center;" in compact_css
    assert ".prompt-remix-preset-form{display:flex;align-items:center;gap:8px;flex-wrap:wrap}" in compact_css
    assert ".prompt-remix-reference-section{display:flex;flex-direction:column;" in compact_css
    assert "export function buildSlotValueRecord" in prompt_template_utils
    assert "if (loading) return null;" in panel
    assert "prompt-direct-image-panel" in panel
    assert "fallbackPromptText" in panel
    assert "prompt-remix-init" not in panel


def test_admin_app_hosts_template_ops_and_review_surface():
    admin = (ROOT / "frontend" / "src" / "AdminApp.tsx").read_text()
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "const normalizedPathname = basePath && basePath !== '/' && pathname.startsWith(basePath)" in main
    assert "const isAdminRoute = normalizedPathname === '/admin' || normalizedPathname.startsWith('/admin/')" in main
    assert "{isAdminRoute ? <AdminApp /> : <App />}" in main
    assert "api.adminSession()" in admin
    assert "api.adminLogin(password.trim())" in admin
    assert "api.adminLogout()" in admin
    assert "api.adminPromptTemplateOpsItems" in admin
    assert "api.adminPromptTemplate(selectedItemId)" in admin
    assert "api.adminInitPromptTemplate(itemId)" in admin
    assert "api.adminBatchInitPromptTemplates" in admin
    assert "api.adminApprovePromptTemplate" in admin
    assert "api.adminRejectPromptTemplate" in admin
    assert "api.adminPromptTemplateFailures" in admin
    assert "api.adminPromptTemplateFailure" in admin
    assert "templateOpsCenter" in admin
    assert "adminPromptTemplates" in admin
    assert "adminAuthTitle" in admin
    assert "adminPasswordLabel" in admin
    assert "templateReviewApprove" in admin
    assert "templateReviewReject" in admin
    assert "templateQueuePendingReview" in admin
    assert "template-failure-layout" in admin
    assert "template-failure-detail-section" in admin
    assert "api.adminPromptTemplateOpsItems" not in config
    assert "adminSession: () => json<AdminSessionRecord>" in client
    assert "adminLogin: (password: string)" in client
    assert "adminLogout: () => json<AdminSessionRecord>" in client
    assert "adminPromptTemplateOpsItems: (params: { status?: string[]; limit?: number } = {})" in client
    assert "adminBatchInitPromptTemplates: (payload: PromptTemplateBatchInitRequest)" in client
    assert "adminPromptTemplateFailures: (limit = 50)" in client
    assert "adminPromptTemplateFailure: (failureId: string)" in client
    assert "adminPromptTemplate: (itemId: string)" in client
    assert "adminApprovePromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {})" in client
    assert "adminRejectPromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {})" in client
    assert "export interface PromptTemplateOpsItem" in types
    assert "export interface PromptTemplateBatchInitResponse" in types
    assert "export interface PromptTemplateReviewRequest" in types
    assert "export interface AdminLoginRequest" in types
    assert "export interface AdminSessionRecord" in types
    assert "export interface PromptWorkflowFailureRecord" in types
    assert "adminPromptTemplates" in i18n
    assert "adminAuthTitle" in i18n
    assert "adminPasswordLabel" in i18n
    assert "templateQueuePendingReview" in i18n
    assert "templateReviewApprove" in i18n
    assert "templateReviewReject" in i18n
    assert ".config-section-head{display:flex;align-items:flex-start;justify-content:space-between;" in compact_css
    assert ".admin-shell{min-height:100vh;padding:30px;" in compact_css
    assert ".admin-auth-card{width:min(480px,100%);display:grid;gap:14px;" in compact_css
    assert ".admin-review-layout{display:grid;grid-template-columns:minmax(300px,.92fr)minmax(420px,1.08fr);" in compact_css
    assert ".admin-template-review{display:grid;gap:12px;" in compact_css
    assert ".admin-review-notes{width:100%;min-height:104px;" in compact_css


def test_topbar_uses_attached_header_logo_branding():
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    logo_asset = ROOT / "frontend" / "src" / "assets" / "header-logo.png"
    assert "../assets/header-logo.png" in topbar
    assert "className=\"logo-mark\"" in topbar
    assert "alt=\"\"" in topbar
    assert "Image Prompt Library" in topbar
    assert "<b>Prompt Library</b>" not in topbar
    assert "ChatGPT Image2 reference" not in topbar
    assert "Sparkles" not in topbar
    assert logo_asset.exists()
    # Edward explicitly asked to use the latest attached logo image, not a cropped/optimized derivative.
    assert logo_asset.stat().st_size > 80_000
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is available in the project test env.
        Image = None
    if Image is not None:
        with Image.open(logo_asset) as img:
            assert img.size == (578, 578)
            assert img.mode == "RGBA"
            assert img.getchannel("A").getextrema()[0] == 0
    compact_css = css.replace(" ", "")
    assert ".logo{display:flex;align-items:center;gap:12px;padding:0;background:transparent;border:0;box-shadow:none;white-space:nowrap}" in compact_css
    assert ".logo-mark" in css
    assert "width:64px" in css
    assert "height:64px" in css


def test_explore_is_thumbnail_constellation_with_configurable_budgets():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "thumbnail-constellation" in explore
    assert "constellation-canvas" in explore
    assert "constellation-cluster-card" in explore
    assert "constellation-thumb-card" in explore
    assert "GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY" in app
    assert "FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY" in app
    assert "globalThumbnailBudget" in app and "focusThumbnailBudget" in app
    assert "t('globalThumbnailBudget')" in config
    assert "t('focusThumbnailBudget')" in config
    assert "allocateGlobalThumbnailBudget" in explore
    assert "minimumAllocation" in explore
    assert ".thumbnail-constellation" in css
    assert ".constellation-thumb-card" in css
    assert ".cluster-orbit{" not in css


def test_explore_focus_mode_stays_in_map_without_duplicate_focus_panel():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "const focusCluster = (c: ClusterRecord) => { setClusterId(c.id); updateView('explore')" in app
    assert "focusedClusterId" in explore
    assert "constellation-focus-panel" not in explore
    assert ".constellation-focus-panel" not in css
    assert "onOpenClusterCards" not in explore
    assert "centerFocusedCluster" in explore


def test_explore_uses_real_thumbnails_not_dots_or_originals():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "function getConstellationImagePaths" in explore
    assert "selectPrimaryImage([item.first_image])" in explore
    assert "imageThumbnailPaths(primaryImage)" in explore
    assert "imagePaths: getConstellationImagePaths(item)" in explore
    assert "lod-dot" not in explore
    assert "node-placeholder" not in explore
    assert "loading=\"lazy\"" in explore
    assert "decoding=\"async\"" in explore
    assert ".orbit-node.lod-dot" not in css


def test_global_explore_fits_viewport_and_cards_remain_scrollable():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "className={`app ${view === 'explore' ? 'explore-mode' : 'cards-mode'}`}" in app
    assert "<main className=\"app-main\">" in app
    assert ".app.explore-mode{height:100vh;overflow:hidden;display:flex;flex-direction:column}" in compact_css
    assert ".app.explore-mode .app-main{flex:1;min-height:0;width:100%;padding:" in css
    assert ".app.explore-mode .thumbnail-constellation{height:100%;min-height:0}" in css
    assert ".app.cards-mode" not in css
    assert "main{max-width:1680px;margin:0auto;padding:26px30px88px}" in compact_css


def test_explore_has_lightweight_hover_preview_without_layout_mutation():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "'--node-rotation': `${node.rotation}deg`" in explore
    assert "transform: `translate(-50%, -50%) rotate(${node.rotation}deg)`" not in explore
    assert "transform:translate(-50%,-50%)rotate(var(--node-rotation,0deg))" in compact_css
    assert "@media(hover:hover)and(pointer:fine)" in compact_css
    assert ".thumbnail-constellation .constellation-thumb-card:hover" in css
    assert ".thumbnail-constellation .constellation-thumb-card:focus-visible" in css
    assert ".thumbnail-constellation:not(.is-focused) .constellation-thumb-card:hover" not in css
    assert "scale(1.42)" in css
    assert "will-change:transform" in css
    assert "width:" not in css.split("@media (hover: hover) and (pointer: fine)", 1)[-1].split("}", 1)[0]
    assert "height:" not in css.split("@media (hover: hover) and (pointer: fine)", 1)[-1].split("}", 1)[0]


def test_item_editor_supports_quick_capture_inputs():
    modal = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = compact(css)

    assert "function inferTitleFromFilename(filename: string): string | null" in modal
    assert "const genericNames = new Set(['image', 'photo', 'picture', 'clipboard', 'pasted image', 'screenshot']);" in modal
    assert "function imageFilesFromClipboard(clipboardData: DataTransfer | null | undefined): File[]" in modal
    assert "window.addEventListener('paste', handlePaste);" in modal
    assert "window.removeEventListener('paste', handlePaste)" in modal
    assert "target.closest('textarea, input:not([type=\"file\"])')" in modal
    assert "event.preventDefault();" in modal
    assert "assignImageFile(role, clipboardImage);" in modal
    assert "const role: UploadImageRole = !hasExistingResultImage && !resultFile" in modal
    assert "onDragOver={onZoneDragOver('result_image')}" in modal
    assert "onDrop={onZoneDrop('result_image')}" in modal
    assert "onDragOver={onZoneDragOver('reference_image')}" in modal
    assert "onDrop={onZoneDrop('reference_image')}" in modal
    assert "className={`drop-zone ${missingRequiredImage ? 'required' : ''} ${resultDropActive ? 'drag-active' : ''}`}" in modal
    assert "className={`drop-zone reference-drop-zone ${referenceDropActive ? 'drag-active' : ''}`}" in modal
    assert "<span className=\"drop-zone-hint\">{t('imageCaptureHint')}</span>" in modal
    assert "setSaveError(t('imageFileOnly'));" in modal
    assert "if (suggestion) setTitle(suggestion);" in modal

    assert "| 'imageCaptureHint' | 'imageFileOnly'" in i18n
    assert "imageCaptureHint: '拖放、貼上，或點擊選擇圖片'" in i18n
    assert "imageCaptureHint: '拖放、粘贴，或点击选择图片'" in i18n
    assert "imageCaptureHint: 'Drop, paste, or click to choose an image'" in i18n
    assert "imageFileOnly: '請選擇圖片檔案。'" in i18n
    assert "imageFileOnly: '请选择图片文件。'" in i18n
    assert "imageFileOnly: 'Please choose an image file.'" in i18n

    assert ".drop-zone.drag-active{border-color:rgba(109,74,255,.52);background:#f5f1ff;" in compact_css
    assert ".drop-zone.required.drag-active{border-color:#d66a49;background:#fff1e9;" in compact_css
    assert ".drop-zone-hint{font-size:12px;font-weight:900;" in compact_css
    assert ".form-error{margin:-4px18px16px;color:#9a3412;" in compact_css


def test_item_editor_supports_prompt_intake_parser_panel():
    modal = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    intake = (ROOT / "frontend" / "src" / "utils" / "promptIntake.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = compact(css)

    assert "import { parsePromptIntake, type PromptIntakeDraft } from '../utils/promptIntake';" in modal
    assert "const [intakeUrl, setIntakeUrl] = useState(item?.source_url || '');" in modal
    assert "const [intakeText, setIntakeText] = useState('');" in modal
    assert "const [intakeFeedback, setIntakeFeedback]" in modal
    assert "const [intakeLoading, setIntakeLoading] = useState(false);" in modal
    assert "const [intakePreview, setIntakePreview] = useState<PromptIntakeDraft | null>(null);" in modal
    assert "const [intakeImageCandidates, setIntakeImageCandidates] = useState<CaseIntakeImageCandidate[]>([]);" in modal
    assert "const [selectedIntakeImageUrl, setSelectedIntakeImageUrl] = useState('');" in modal
    assert "const [candidateImageLoadingUrl, setCandidateImageLoadingUrl] = useState('');" in modal
    assert "const [failedIntakeImageUrls, setFailedIntakeImageUrls] = useState<string[]>([]);" in modal
    assert "const applyIntakeDraft = (draft: PromptIntakeDraft) => {" in modal
    assert "const buildPromptIntakePreview = (text = intakeText) => {" in modal
    assert "const previewPromptIntake = (text = intakeText) => {" in modal
    assert "const applyPromptIntake = (draft = intakePreview || buildPromptIntakePreview()) => {" in modal
    assert "const importIntakeImageCandidate = async (candidate: CaseIntakeImageCandidate) => {" in modal
    assert "const fetchPromptIntake = async () => {" in modal
    assert "const fetched = await api.fetchCaseIntake(intakeUrl.trim());" in modal
    assert "setIntakeUrl(fetched.final_url);" in modal
    assert "setIntakeText(fetched.intake_text);" in modal
    assert "const candidates = fetched.image_candidates?.length" in modal
    assert "setIntakeImageCandidates(candidates);" in modal
    assert "const draft = parsePromptIntake(fetched.intake_text);" in modal
    assert "const imageFile = await api.fetchCaseIntakeImage(candidate.url);" in modal
    assert "assignImageFile('reference_image', imageFile);" in modal
    assert "setSelectedIntakeImageUrl(candidate.url);" in modal
    assert "setIntakeFeedback({ tone: 'success', message: t('promptIntakePreviewReady') });" in modal
    assert "setIntakeFeedback({ tone: 'success', message: t('promptIntakePreviewReadyWithImages') });" in modal
    assert "setIntakeFeedback({ tone: 'success', message: t('promptIntakeImagesReady') });" in modal
    assert "setIntakeFeedback({ tone: 'success', message: t('promptIntakeImageImported') });" in modal
    assert "setIntakeFeedback({ tone: 'error', message: normalizeIntakeError(error) });" in modal
    assert "setIntakeFeedback({ tone: 'error', message: t('promptIntakeEmpty') });" in modal
    assert "setIntakeFeedback({ tone: 'error', message: t('promptIntakeNoMatch') });" in modal
    assert "setIntakeFeedback({ tone: 'error', message: t('promptIntakeUrlEmpty') });" in modal
    assert "setIntakeFeedback({ tone: 'success', message: t('promptIntakeApplied') });" in modal
    assert "className=\"field prompt-field intake-field\"" in modal
    assert "className=\"intake-url-row\"" in modal
    assert "className=\"intake-textarea\"" in modal
    assert "className=\"intake-preview\"" in modal
    assert "className=\"intake-preview-grid\"" in modal
    assert "className=\"intake-preview-card\"" in modal
    assert "className=\"intake-image-candidates\"" in modal
    assert "className=\"intake-image-candidate-grid\"" in modal
    assert "className={`intake-image-candidate ${selectedIntakeImageUrl === candidate.url ? 'is-selected' : ''}`}" in modal
    assert "src={caseIntakeImageUrl(candidate.url)}" in modal
    assert "className=\"intake-image-fallback\"" in modal
    assert "className=\"intake-actions\"" in modal
    assert "className=\"intake-action-buttons\"" in modal
    assert "className=\"intake-help\"" in modal
    assert "className=\"secondary intake-fetch-button\"" in modal
    assert "className=\"secondary intake-button\"" in modal
    assert "className=\"secondary intake-apply-button\"" in modal
    assert "className={`form-feedback ${intakeFeedback.tone}`}" in modal
    assert "fetchCaseIntake: (_url: string) => Promise.reject(new Error('URL intake is unavailable in the online sandbox. Run the app locally to fetch case pages.'))" in api_client
    assert "fetchCaseIntakeImage: (_url: string) => Promise.reject(new Error('Remote image intake is unavailable in the online sandbox. Run the app locally to fetch case pages.'))" in api_client
    assert "fetchCaseIntake: (url: string) => json<CaseIntakeFetchResult>('/api/intake/fetch'" in api_client
    assert "export const caseIntakeImageUrl = (url: string) => `/api/intake/image?url=${encodeURIComponent(url)}`;" in api_client
    assert "fetchCaseIntakeImage: (url: string) => fileFromUrl(caseIntakeImageUrl(url))" in api_client
    assert "async function fileFromUrl(url: string, init?: RequestInit): Promise<File>" in api_client
    assert "export interface CaseIntakeImageCandidate { url: string; source: string; alt?: string }" in types
    assert "export interface CaseIntakeFetchResult { url: string; final_url: string; title?: string; description?: string; author?: string; image_url?: string; image_candidates?: CaseIntakeImageCandidate[]; intake_text: string }" in types
    assert "export function parsePromptIntake(input: string): PromptIntakeDraft | null" in intake
    assert "const INLINE_PATTERNS" in intake
    assert "const HEADING_ALIASES" in intake
    assert "extractHashtags" in intake
    assert "inferPromptField" in intake

    assert "| 'promptIntake' | 'promptIntakeHelp' | 'promptIntakePlaceholder' | 'promptIntakeUrlPlaceholder' | 'fetchPromptIntake' | 'promptIntakeFetching' | 'extractPromptDraft' | 'promptIntakeApplyDraft' | 'promptIntakePreview' | 'promptIntakePreviewHelp' | 'promptIntakePreviewReady' | 'promptIntakePreviewReadyWithImages' | 'promptIntakeImagesReady' | 'promptIntakeApplied' | 'promptIntakeAppliedWithImage' | 'promptIntakeAppliedImageSkipped' | 'promptIntakeImageImported' | 'promptIntakeImageImportFailed' | 'promptIntakeImageCandidates' | 'promptIntakeImageCandidatesHelp' | 'promptIntakeImageCandidateAlt' | 'promptIntakeImageImporting' | 'promptIntakeImageRecommended' | 'promptIntakeImageLoadFailed' | 'usePromptIntakeImage' | 'promptIntakeFieldsDetected' | 'promptIntakePromptLanguages' | 'promptIntakeFieldEmpty' | 'promptIntakeEmpty' | 'promptIntakeNoMatch' | 'promptIntakeUrlEmpty' | 'promptIntakeUrlInvalid' | 'promptIntakeFetchBlocked' | 'promptIntakeFetchFailed'" in i18n
    assert "promptIntake: '案例導入'" in i18n
    assert "promptIntake: '案例导入'" in i18n
    assert "promptIntake: 'Case intake'" in i18n
    assert "fetchPromptIntake: 'Fetch URL'" in i18n
    assert "promptIntakePreview: 'Import preview'" in i18n
    assert "promptIntakePreviewReady: 'The intake preview is ready to review and apply.'" in i18n
    assert "promptIntakeImagesReady: 'The page was fetched. Choose a candidate image below.'" in i18n
    assert "promptIntakeApplyDraft: 'Apply to form'" in i18n
    assert "promptIntakeImageImported: 'The selected page image was imported as the reference image.'" in i18n
    assert "promptIntakeImageCandidates: 'Candidate images'" in i18n
    assert "usePromptIntakeImage: 'Use this image'" in i18n
    assert "promptIntakeImageImportFailed: 'This candidate image could not be imported.'" in i18n
    assert "promptIntakeImageLoadFailed: 'Thumbnail unavailable'" in i18n
    assert "promptIntakeFetchBlocked: 'The case page could not be fetched. The source may block requests or be temporarily unavailable.'" in i18n
    assert "promptIntakeUrlEmpty: 'Enter a case URL first.'" in i18n
    assert "extractPromptDraft: 'Build preview'" in i18n
    assert "promptIntakeNoMatch: 'No recognizable fields were found in the pasted text.'" in i18n

    assert ".intake-field{grid-column:1/-1;padding:16px;border:1pxsolidvar(--border);" in compact_css
    assert ".intake-url-row{display:grid;grid-template-columns:minmax(0,1fr)auto;gap:10px}" in compact_css
    assert ".intake-fetch-button,.intake-button,.intake-apply-button{font-weight:850;flex:00auto}" in compact_css
    assert ".intake-textarea{min-height:152px}" in compact_css
    assert ".intake-actions{display:flex;align-items:flex-start;justify-content:space-between;" in compact_css
    assert ".intake-action-buttons{display:flex;align-items:center;gap:10px;flex-wrap:wrap}" in compact_css
    assert ".intake-preview{display:grid;gap:12px;padding:14px;" in compact_css
    assert ".intake-preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}" in compact_css
    assert ".intake-image-candidates{display:grid;gap:10px;" in compact_css
    assert ".intake-image-candidate-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(126px,1fr));gap:10px}" in compact_css
    assert ".intake-image-candidate.is-selected{border-color:#d4c59e;" in compact_css
    assert ".intake-image-candidateimg,.intake-image-fallback{width:100%;aspect-ratio:4/3;border-radius:12px}" in compact_css
    assert ".intake-help{margin:0;color:var(--muted);font-size:12px;" in compact_css
    assert ".form-feedback.success{color:#166534}" in compact_css
    assert ".form-feedback.error{color:#9a3412}" in compact_css


def test_explore_has_static_repulsive_relaxation_and_tap_drag_threshold():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    assert "TAP_DRAG_THRESHOLD" in explore
    assert "tapTarget" in explore
    assert "dragged:" in explore
    assert "Math.hypot" in explore
    assert "settleCollisionAwarePositions" in explore
    assert "doesCollide" in explore
    assert "spiralStep" in explore
    assert "relaxConstellationNodes" in explore
    assert "RELAXATION_ITERATIONS = 120" in explore
    assert "REPULSION_STRENGTH = 0.42" in explore
    assert "CLUSTER_REPULSION_STRENGTH = 0.52" in explore
    assert "SPRING_STRENGTH = 0.025" in explore
    assert "const collisionPadding = 18" in explore
    assert "const baseRadius = focused ? 220 : 146" in explore
    assert "const radiusStep = focused ? 23 : 14" in explore
    assert "repelAgainstClusterHubs" in explore
    assert "clampRelaxedNode" in explore
    assert "GLOBAL_THUMB_WIDTH = 88" in explore
    assert "GLOBAL_THUMB_HEIGHT = 112" in explore
    assert "buildCompactFocusSlots" in explore
    assert "FOCUS_SLOT_GAP = 16" in explore
    assert "slotStepX" in explore and "slotStepY" in explore
    assert "Math.hypot((x - pos.x) * 0.78, (y - pos.y) * 1.35)" in explore
    assert "rotation: 0" in explore
    assert "() => (focusedClusterId ? constellation.filter(cluster => !cluster.inactive) : constellation)" in explore
    assert "resolveConstellationNodeOverlaps" in explore
    assert "placeWithoutGlobalOverlap" in explore
    assert "attempt <= 1800" in explore
    assert "'--node-rotation': `${node.rotation}deg`" in explore
    assert "continuous physics" not in explore.lower()


def test_filter_refresh_keeps_stale_content_without_large_loading_flash():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    hook = (ROOT / "frontend" / "src" / "hooks" / "useItemsQuery.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "initialLoading" in hook
    assert "refreshing" in hook
    assert "setInitialLoading" in hook
    assert "setRefreshing" in hook
    assert "dataScope" in hook
    assert "setDataScope" in hook
    assert "return { data, loading, initialLoading, refreshing, error, dataScope }" in hook
    assert "const { data, loading, initialLoading, refreshing, error, dataScope }" in app
    assert "pendingExploreUnfilterClusterId" in app
    assert "exploreUnfilterFadePhase" in app
    assert "'out' | 'pre-in' | 'in' | 'idle'" in app
    assert "dataScope.clusterId === pendingExploreUnfilterClusterId" in app
    assert "setPendingExploreUnfilterClusterId(clusterId)" in app
    assert "setExploreUnfilterFadePhase('out')" in app
    assert "setExploreUnfilterFadePhase('pre-in')" in app
    assert "requestAnimationFrame(() => setExploreUnfilterFadePhase('in'))" in app
    assert "setExploreUnfilterFadePhase('idle')" in app
    assert "unfilterTransitionPhase={exploreUnfilterFadePhase}" in app
    assert "useEffect(() => {" in app and "setPendingExploreUnfilterClusterId(undefined)" in app
    assert "exploreFocusedClusterId" in app
    assert "dataScope.clusterId" in app
    assert "exploreFitRequestKey" in app
    assert "setExploreFitRequestKey" in app
    assert "clearCluster = () => {" in app
    clear_body = app.split("const clearCluster = () => {", 1)[1].split("  const saved =", 1)[0]
    assert "setExploreFitRequestKey" not in clear_body
    assert "app-main ${refreshing ? 'is-refreshing' : ''}" in app
    assert "aria-busy={refreshing}" in app
    assert "initialLoading && <div className=\"loading\">" in app
    assert "loading && <div className=\"loading\">" not in app
    assert "refresh-indicator" in app
    assert ".app-main.is-refreshing" in css
    assert ".refresh-indicator" in css


def test_constellation_card_drag_pans_viewport_and_disables_native_image_drag():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "type GestureState" in explore
    assert "panStartOffset" in explore
    assert "startGesture" in explore
    assert "moveGesture" in explore
    assert "finishGesture" in explore
    assert "setPointerCapture" in explore
    assert "setOffset({ x: gesture.panStartOffset.x +" in explore
    assert "dragging: true" in explore
    assert "draggable={false}" in explore
    assert "event.stopPropagation()" not in explore
    assert "onPointerDown={(event) => startGesture(event, { type: 'cluster', cluster })}" in explore
    assert "onPointerDown={(event) => startGesture(event, { type: 'item', item: node.item })}" in explore
    assert ".constellation-thumb-card,.constellation-thumb-card img,.constellation-cluster-card" in css
    assert "-webkit-user-drag:none" in css.replace(" ", "")
    assert "user-select:none" in css.replace(" ", "")


def test_constellation_blank_canvas_and_svg_drag_start_pan_without_stealing_card_taps():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    assert "function isBlankConstellationPointerTarget" in explore
    assert "target.closest('.constellation-thumb-card, .constellation-cluster-card, button, a, input, textarea, select')" in explore
    assert "target.closest('.constellation-canvas, .constellation-links')" in explore
    assert "if (!isBlankConstellationPointerTarget(event.target, event.currentTarget)) return;" in explore
    assert "event.target !== event.currentTarget" not in explore


def test_modal_and_explore_focus_use_reduced_motion_safe_transitions():
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "FOCUS_TRANSITION_MS" in explore
    assert "setIsFocusAnimating" in explore
    assert "focus-animation" in explore
    assert "window.setTimeout" in explore
    assert "centerFocusedCluster" in explore
    assert "className={`constellation-canvas ${isFocusAnimating ? 'focus-animation' : ''}`}" in explore
    assert "viewportRef" in explore
    assert "getConstellationBounds(displayedClusters)" in explore
    assert "computeFitTransform" in explore
    assert "fitConstellationToViewport" in explore
    assert "Math.min(1.15, Math.max(0.42" in explore
    assert "useLayoutEffect" in explore
    assert "[focusedClusterId, displayedClusters, fitRequestKey]" in explore
    assert "fitRequestKey" in explore
    assert "lastFitRequestKeyRef" in explore
    assert "unfilterTransitionPhase" in explore
    assert "is-unfilter-fade-out" in explore
    assert "is-unfilter-fade-pre-in" in explore
    assert "is-unfilter-fade-in" in explore
    assert "isFocusAnimating" in explore
    assert "focusedClusterId || fitRequestKey" in explore
    assert "@keyframes modal-backdrop-in" in css
    assert "@keyframes modal-panel-in" in css
    assert "@keyframes modal-content-in" in css
    assert "modal-content-enter" in (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    assert "animation:modal-backdrop-in" in css.replace(" ", "")
    assert "animation:modal-panel-in" in css.replace(" ", "")
    assert "animation:modal-content-in" in css.replace(" ", "")
    assert ".detail.modal" in css and "min-height:min" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".constellation-canvas.focus-animation" in css
    assert ".thumbnail-constellation.is-unfilter-fade-out .constellation-canvas" in css
    assert ".thumbnail-constellation.is-unfilter-fade-in .constellation-canvas" in css
    assert "transition:opacity .14s ease" in css


def test_empty_library_states_have_inline_first_prompt_cta():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "openNewItemEditor" in app
    assert "onAdd={isDemoMode ? undefined : openNewItemEditor}" in app
    assert "!isDemoMode && <button className=\"fab\"" in app
    assert "t('libraryEmptyTitle')" in explore
    assert "t('addFirstPrompt')" in explore
    assert "onAdd" in explore
    assert "t('addFirstPrompt')" in cards
    assert "onAdd" in cards
    assert "empty-actions" in css


def test_cards_keep_adaptive_masonry_and_actions():
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "masonry-like" in cards
    assert "breakInside" in card
    assert "t('copyPrompt')" in card
    assert "t('favorite')" in card
    assert "t('edit')" in card
    assert "onFavorite" in card and "onEdit" in card
    assert "column-width:var(--card-min)" in css.replace(" ", "")
    assert "break-inside:avoid" in css.replace(" ", "")


def test_cards_reserve_image_aspect_ratio_before_lazy_decode():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "imageAspectRatio" in card
    assert "primaryImage?.width" in card
    assert "primaryImage?.height" in card
    assert "aspectRatio: imageAspectRatio" in card
    assert "card-image-frame" in card
    assert "has-reserved-ratio" in card
    assert "natural-ratio" in card
    assert "width={primaryImage?.width || undefined}" in card
    assert "height={primaryImage?.height || undefined}" in card
    assert ".card-image-frame" in css
    assert "aspect-ratio:var(--card-image-ratio" in css.replace(" ", "")
    assert ".card-image-frame img" in css
    assert "height:100%" in css


def test_copy_prompt_uses_shared_preferred_language_resolver():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    utils = (ROOT / "frontend" / "src" / "utils" / "prompts.ts").read_text()
    clipboard = (ROOT / "frontend" / "src" / "utils" / "clipboard.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "PromptLanguage" in utils
    assert "resolvePromptText" in utils
    assert "copyTextToClipboard" in clipboard
    assert "preferredLanguage" in app
    assert "preferred_prompt_language" in app
    assert "zh_hant" in config and "zh_hans" in config and "en" in config
    assert "onCopyPrompt" in card and "prompt_snippet || item.title" not in card
    assert "toast" in app
    assert "showCopyToast" in app
    assert "copySuccess" in app
    assert "copyFailed" in app
    assert "toast copy-toast elegant-toast" in app
    assert "toast-icon" in app and "toast-title" in app
    assert ".elegant-toast" in css
    assert "backdrop-filter:blur" in css
    assert "@keyframes toast-in" in css
    assert "resolvePromptText" in detail
    assert "preferredLanguage" in detail
    assert "const copyText = prompt?.text || resolvedPrompt?.text || resolvePromptText" in detail
    assert "onCopyPrompt" in detail
    assert "copyTextToClipboard(text)" in detail
    assert "setCopyFeedback" not in detail


def test_ui_language_setting_localizes_main_chrome():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    topbar = (ROOT / "frontend" / "src" / "components" / "TopBar.tsx").read_text()
    cards = (ROOT / "frontend" / "src" / "components" / "CardsView.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "UI_LANGUAGE_STORAGE_KEY" in app
    assert "loadUiLanguage" in app
    assert "uiLanguage" in app and "setUiLanguage" in app
    assert "onUiLanguage" in config
    assert "t('uiLanguage')" in config
    assert "t={t}" in app
    assert "t('filters')" in topbar
    assert "t('searchPlaceholder')" in topbar
    assert "t('noMatchingPrompts')" in cards
    assert "export type UiLanguage = 'zh_hant' | 'zh_hans' | 'en'" in i18n
    assert "繁體中文" in i18n and "简体中文" in i18n and "English" in i18n
    assert "搜尋所有 prompts、標題、標籤…" in i18n
    assert "Search all prompts, titles, tags…" in i18n
    assert "嘅" not in i18n and "搵" not in i18n and "吓" not in i18n and "幾多" not in i18n
    assert "Explore 全部 collection 的整體密度。" in i18n


def test_item_editor_uses_ui_language_for_long_tail_strings():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "<ItemEditorModal t={t}" in app
    assert "t: Translator" in editor
    assert "t('newReference')" in editor
    assert "t('editPromptCard')" in editor
    assert "t('title')" in editor
    assert "t('traditionalChinesePrompt')" in editor
    assert "t('resultImageRequired')" in editor
    assert "t('referencePhotoOptional')" in editor
    assert "t('deleteReference')" in editor
    assert "t('saveReference')" in editor
    assert "Delete reference" not in editor
    assert "Save reference" not in editor
    assert "香港" not in i18n
    assert "完成圖片為必填" in i18n


def test_detail_modal_dedupes_image_rail_and_hides_single_image_rail():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    assert "uniqueImages" in detail
    assert "getImageIdentity" in detail
    assert "seenImageKeys" in detail
    assert "selectPrimaryImage(uniqueImages)" in detail
    assert "uniqueImages.length > 1" in detail
    assert "uniqueImages.map" in detail
    assert "item.images.map" not in detail


def test_filters_and_explore_budget_controls_match_vista_style():
    filters = (ROOT / "frontend" / "src" / "components" / "FiltersPanel.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "filter-drawer" in filters
    assert "filter-search" in filters
    assert "filter-pill-grid" in filters
    assert "Collections" in filters
    assert "t('allReferences')" in filters
    assert "collectionQuery" in filters
    assert "filteredClusters" in filters
    assert "t('noCollectionsFound')" in filters
    assert "Use clusters as quick filter chips" not in filters
    assert "Templates</h2>" not in filters
    assert "onClear" in filters and "clearCluster" in app
    assert "handleFilterSelect" in app
    assert "view === 'explore' ? focusCluster(c) : selectCluster(c)" in app
    assert "type=\"range\"" in config
    assert "range-setting" in config
    assert "range-ticks" in config
    assert "GLOBAL_BUDGET_MIN = 50" in config
    assert "GLOBAL_BUDGET_MAX = 150" in config
    assert "FOCUS_BUDGET_MIN = 24" in config
    assert "FOCUS_BUDGET_MAX = 100" in config
    assert ".filter-drawer" in css
    assert ".filter-pill-grid" in css
    assert ".filter-empty" in css
    assert ".range-setting" in css
    assert ".range-ticks" in css


def test_drawer_close_buttons_use_shared_polished_panel_close_style():
    filters = (ROOT / "frontend" / "src" / "components" / "FiltersPanel.tsx").read_text()
    config = (ROOT / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "className=\"panel-close\"" in filters
    assert "className=\"panel-close\"" in config
    assert ".panel-close" in css
    assert "width:38px" in css
    assert "border-radius:999px" in css
    assert "aria-label={t('closeFilters')}" in filters
    assert "aria-label={t('closeConfig')}" in config


def test_copy_prompt_has_insecure_lan_clipboard_fallback():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    clipboard = (ROOT / "frontend" / "src" / "utils" / "clipboard.ts").read_text()
    assert "navigator.clipboard?.writeText" not in app
    assert "navigator.clipboard?.writeText" not in detail
    assert "navigator.clipboard?.writeText" in clipboard
    assert "document.execCommand('copy')" in clipboard
    assert "textarea.select()" in clipboard


def test_gallery_visuals_are_polished():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    assert "modal-hero" in detail and "prompt-block" in detail
    assert "editor-grid" in editor and "drop-zone" in editor
    assert "--surface-warm" in css
    assert ".fab{position:fixed;right:32px;bottom:32px" in css.replace("\n", "")


def test_detail_modal_supports_inline_editing_contract():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "onChanged" in detail and "onChanged={saved}" in app
    assert "detail-side-actions" in detail
    assert "detail-side-primary-actions" in detail
    assert "modal-icon-button favorite-button" in detail
    assert "modal-icon-button edit-button" in detail
    assert "modal-icon-button close" in detail
    assert detail.index("detail-side-actions") < detail.index("collection-inline-edit")
    assert "aria-label={item.favorite ? t('saved') : t('favorite')}" in detail
    assert "aria-label={t('edit')}" in detail
    assert ".modal-icon-button:hover" in css
    assert ".modal-icon-button:focus-visible" in css
    assert "InlineEditableField" in detail
    assert "InlineEditableTextArea" in detail
    assert "title-inline-edit" in detail
    assert ".title-inline-edit{display:inline-block;min-width:min(100%,260px);font-size:clamp(24px,2.8vw,38px);line-height:1.08;letter-spacing:-.045em}" in compact_css
    assert ".title-inline-editinput{font-size:inherit;line-height:inherit;letter-spacing:inherit" in compact_css
    assert "collection-inline-edit" in detail
    assert "metadata-inline-edit" in detail
    assert "prompt-inline-edit" in detail
    assert "notes-inline-edit" in detail
    assert "inline-edit-controls" in css
    assert "Check" in detail and "X" in detail
    assert "commitInlineUpdate" in detail
    assert "api.updateItem(item.id" in detail
    assert "promptDisplayOrder = ['en', 'zh_hant', 'zh_hans']" in detail
    assert "prompt-edit-icon" in detail
    assert "role=\"tablist\"" in detail
    assert "aria-selected={lang === promptLanguage}" in detail
    assert "availablePromptRecords" in detail
    assert "resolvePromptRecord" in detail
    assert "lastDefaultPromptKeyRef" in detail
    assert "const defaultPromptKey = `${id}:${preferredLanguage}`" in detail
    assert "lastDefaultPromptKeyRef.current === defaultPromptKey" in detail
    assert "lastDefaultPromptKeyRef.current = defaultPromptKey" in detail
    assert "setLang(nextPrompt.language)" in detail
    assert "const prompt = item?.prompts.find(promptRecord => promptRecord.language === lang)" in detail
    assert "const resolvedPrompt = resolvePromptRecord(availablePromptRecords, lang, preferredLanguage)" in detail
    assert "promptDisplayOrder.map(promptLanguage" in detail
    assert "const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage)" in detail
    assert "onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}" in detail
    assert "disabled={!tabPrompt?.text.trim()}" not in detail
    assert "availablePromptRecords.map(promptOption" not in detail
    assert "<section className=\"prompt-block prompt-panel active\">" in detail
    assert "prompt-edit-controls" in detail and "prompt-edit-controls" in css
    assert "copyTextToClipboard(text)" in detail
    assert "promptRecord?.text ? <p>{promptRecord.text}</p>" not in detail
    assert "add-note-affordance\">{t('promptText')}" in detail
    assert "disabled={!prompt?.text}" in detail
    assert "handleCopyPrompt(prompt?.text || '')" in detail
    assert "add-note-affordance" in detail
    assert "t('addNote')" in detail
    assert "source-icon-link" in detail
    assert "ExternalLink" in detail
    assert "touch-action:manipulation" in css
    assert ".close:hover" not in css
    assert ".modal-icon-button.close" in css
    assert ".inline-editable:hover" in css
    assert ".prompt-block" in css
    assert "prompt-copy-icon" in css
    assert "prompt-language-tabs" in css
    assert "background:#fff" in css
    assert "background:#e8e2d5" in css
    assert "top:-6px" in css and "right:-6px" in css
    assert "justify-content:center" in css
    assert "stroke-width:2.6" in css
    assert "border:0" in css
    assert "width:min(94vw,1440px)" in css.replace(" ", "")
    assert "grid-template-columns:minmax(520px,1.15fr)minmax(420px,.85fr)" in css.replace(" ", "")
    assert "prompt-panel-body" in css and "max-height:min(34vh,320px)" in css.replace(" ", "")
    assert "prompt-edit-textarea" in css
    assert ".detail-side-actions" in css


def test_detail_modal_tag_unlink_and_add_controls_are_hover_and_touch_aware():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    compact_css = css.replace(" ", "")
    assert "detail-tag-chip" in detail
    assert "tag-unlink-button" in detail
    assert "add-tag-chip" in detail
    assert "tag-add-input" in detail
    assert "filteredTagSuggestions" in detail
    assert "api.updateItem(item.id" in detail
    assert "item.tags.filter" in detail
    assert ".detail-tag-chip .tag-unlink-button" in css
    assert ".detail-tag-chip:hover .tag-unlink-button" in css
    assert "@media(hover:none),(pointer:coarse)" in compact_css
    assert ".add-tag-chip" in css
    assert ".tag-add-popover" in css


def test_editor_supports_multilingual_prompts_collection_suggestions_and_image_requirements():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()

    assert "clusters={clusters}" in app
    assert "tags={tags}" in app
    assert "clusters: ClusterRecord[]" in editor
    assert "tags: TagRecord[]" in editor
    assert "initialTraditionalPrompt" in editor
    assert "promptText(item, 'zh_hant') || promptText(item, 'original')" in editor
    assert "zhHantPrompt" in editor and "zhHansPrompt" in editor and "englishPrompt" in editor
    assert "language: 'en', text: englishPrompt.trim(), is_primary: true" in editor
    assert "language: 'zh_hant'" in editor
    assert "language: 'zh_hans'" in editor
    assert editor.index("t('englishPrompt')") < editor.index("t('traditionalChinesePrompt')") < editor.index("t('simplifiedChinesePrompt')")
    assert "model" in editor and "setModel" in editor
    assert "author" in editor and "setAuthor" in editor
    assert "sourceUrl" in editor and "setSourceUrl" in editor
    assert "notes" in editor and "setNotes" in editor
    assert "t('imageGeneratedFrom')" in editor
    assert "t('author')" in editor
    assert "t('sourceUrl')" in editor
    assert "t('notes')" in editor
    assert "collection-suggestions" in editor
    assert "filteredClusters" in editor
    assert "list=\"collection-suggestions\"" in editor
    assert "tag-suggestions" in editor
    assert "filteredTags" in editor
    assert "list=\"tag-suggestions\"" in editor
    assert "Original" not in detail
    assert "'original'" not in detail
    assert "t('resultImageRequired')" in editor and "required" in editor
    assert "t('referencePhotoOptional')" in editor and "optional" in i18n.lower()
    assert "resultFile" in editor and "referenceFile" in editor
    assert "hasExistingResultImage" in editor
    assert "image.role === 'result_image'" in editor
    assert "missingRequiredImage" in editor
    assert "createdNewItem" in editor
    assert "api.deleteItem(saved.id)" in editor
    assert "result_image" in types
    assert "reference_image" in types
    assert "role?: UploadImageRole" in types
    assert "fd.set('role', role)" in api_client


def test_frontend_prefers_result_image_for_card_and_detail_hero():
    card = (ROOT / "frontend" / "src" / "components" / "ItemCard.tsx").read_text()
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text()
    explore = (ROOT / "frontend" / "src" / "components" / "ExploreView.tsx").read_text()
    image_utils = (ROOT / "frontend" / "src" / "utils" / "images.ts").read_text()

    assert "selectPrimaryImage" in card
    assert "selectPrimaryImage" in detail
    assert "selectPrimaryImage" in explore
    assert "image?.role === 'result_image'" in image_utils
    assert "item.first_image?.thumb_path" not in card
    assert "const primaryImage = uniqueImages[0]" not in detail


def test_delete_action_archives_item_and_refreshes_visible_data():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    api_client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    editor = (ROOT / "frontend" / "src" / "components" / "ItemEditorModal.tsx").read_text()

    assert "deleteItem" in api_client
    assert "method: 'DELETE'" in api_client
    assert "onDeleted" in app
    assert "setItemsReloadKey(k => k + 1)" in app
    assert "t('deleteReference')" in editor
    assert "confirm(t('deleteReferenceConfirm'))" in editor
    assert "api.deleteItem(item.id)" in editor
    assert "danger" in editor


def test_admin_review_shows_prompt_source_extraction_metadata():
    admin = (ROOT / "frontend" / "src" / "AdminApp.tsx").read_text()
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()
    i18n = (ROOT / "frontend" / "src" / "utils" / "i18n.ts").read_text()
    assert "prompt_source_extracted: boolean" in types
    assert "prompt_source_strategy?: string" in types
    assert "template-source-extraction-card" in admin
    assert "selectedTemplate.prompt_source_extracted" in admin
    assert "selectedTemplate.prompt_source_strategy" in admin
    assert "selectedTemplate.prompt_source_original_length" in admin
    assert "template-source-extraction-card" in css
    assert "templateReviewSourceExtracted" in i18n
    assert "templateReviewSourceStrategy" in i18n
    assert "templateReviewSourceLengths" in i18n
