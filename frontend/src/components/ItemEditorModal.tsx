import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import { ImagePlus, Trash2, X } from 'lucide-react';
import { api, caseIntakeImageUrl } from '../api/client';
import type { CaseIntakeImageCandidate, ClusterRecord, ItemDetail, TagRecord, UploadImageRole } from '../types';
import type { Translator } from '../utils/i18n';
import { parsePromptIntake, type PromptIntakeDraft } from '../utils/promptIntake';

function promptText(item: ItemDetail | undefined, language: string) {
  return item?.prompts.find(prompt => prompt.language === language)?.text || '';
}

function initialTraditionalPrompt(item: ItemDetail | undefined) {
  return promptText(item, 'zh_hant') || promptText(item, 'original');
}

function inferTitleFromFilename(filename: string): string | null {
  const normalized = filename
    .replace(/\.[^/.]+$/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalized) return null;
  const genericNames = new Set(['image', 'photo', 'picture', 'clipboard', 'pasted image', 'screenshot']);
  if (genericNames.has(normalized.toLowerCase())) return null;
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function imageFilesFromList(files: FileList | File[] | null | undefined): File[] {
  if (!files) return [];
  return Array.from(files).filter(file => file.type.startsWith('image/'));
}

function imageFilesFromClipboard(clipboardData: DataTransfer | null | undefined): File[] {
  if (!clipboardData) return [];
  const directFiles = imageFilesFromList(clipboardData.files);
  if (directFiles.length > 0) return directFiles;
  return Array.from(clipboardData.items || [])
    .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
    .map(item => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

function countPromptIntakeFields(draft: PromptIntakeDraft): number {
  return [
    draft.title,
    draft.cluster,
    draft.model,
    draft.author,
    draft.sourceUrl,
    draft.tags.length > 0 ? 'tags' : '',
    draft.englishPrompt,
    draft.traditionalChinesePrompt,
    draft.simplifiedChinesePrompt,
    draft.notes,
  ].filter(Boolean).length;
}

function extractErrorDetail(error: unknown): string {
  if (!(error instanceof Error)) return '';
  let message = error.message.trim();
  if (!message) return '';
  try {
    const parsed = JSON.parse(message);
    if (parsed && typeof parsed === 'object' && 'detail' in parsed && parsed.detail) {
      message = String(parsed.detail).trim();
    }
  } catch {
    // Keep the original error message when the payload is not JSON.
  }
  return message;
}

export default function ItemEditorModal({
  item,
  t,
  clusters,
  tags: existingTags,
  onClose,
  onSaved,
  onDeleted,
}: {
  item?: ItemDetail;
  t: Translator;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [title, setTitle] = useState(item?.title || '');
  const [model, setModel] = useState(item?.model || 'ChatGPT');
  const [author, setAuthor] = useState(item?.author || 'User');
  const [sourceUrl, setSourceUrl] = useState(item?.source_url || '');
  const [notes, setNotes] = useState(item?.notes || '');
  const [cluster, setCluster] = useState(item?.cluster?.name || '');
  const [tags, setTags] = useState(item?.tags.map(t => t.name).join(', ') || '');
  const [zhHantPrompt, setZhHantPrompt] = useState(initialTraditionalPrompt(item));
  const [zhHansPrompt, setZhHansPrompt] = useState(promptText(item, 'zh_hans'));
  const [englishPrompt, setEnglishPrompt] = useState(promptText(item, 'en'));
  const [resultFile, setResultFile] = useState<File>();
  const [referenceFile, setReferenceFile] = useState<File>();
  const [intakeUrl, setIntakeUrl] = useState(item?.source_url || '');
  const [intakeText, setIntakeText] = useState('');
  const [intakeFeedback, setIntakeFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [intakePreview, setIntakePreview] = useState<PromptIntakeDraft | null>(null);
  const [intakeImageCandidates, setIntakeImageCandidates] = useState<CaseIntakeImageCandidate[]>([]);
  const [selectedIntakeImageUrl, setSelectedIntakeImageUrl] = useState('');
  const [candidateImageLoadingUrl, setCandidateImageLoadingUrl] = useState('');
  const [failedIntakeImageUrls, setFailedIntakeImageUrls] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [resultDropActive, setResultDropActive] = useState(false);
  const [referenceDropActive, setReferenceDropActive] = useState(false);

  const hasExistingResultImage = Boolean(item?.images?.some(image => image.role === 'result_image'));
  const hasPrompt = Boolean(zhHantPrompt.trim() || zhHansPrompt.trim() || englishPrompt.trim());
  const missingRequiredImage = !hasExistingResultImage && !resultFile;
  const [saveError, setSaveError] = useState('');
  const filteredClusters = useMemo(() => {
    const query = cluster.trim().toLowerCase();
    if (!query) return clusters.slice(0, 8);
    return clusters.filter(c => c.name.toLowerCase().includes(query)).slice(0, 8);
  }, [cluster, clusters]);
  const filteredTags = useMemo(() => {
    const selected = new Set(tags.split(',').map(t => t.trim()).filter(Boolean));
    const query = tags.split(',').pop()?.trim().toLowerCase() || '';
    return existingTags
      .filter(tag => !selected.has(tag.name) && (!query || tag.name.toLowerCase().includes(query)))
      .slice(0, 10);
  }, [tags, existingTags]);
  const intakePreviewFieldCount = useMemo(() => intakePreview ? countPromptIntakeFields(intakePreview) : 0, [intakePreview]);
  const intakePreviewPromptLanguages = useMemo(() => {
    if (!intakePreview) return [];
    return [
      intakePreview.englishPrompt ? t('englishPrompt') : '',
      intakePreview.traditionalChinesePrompt ? t('traditionalChinesePrompt') : '',
      intakePreview.simplifiedChinesePrompt ? t('simplifiedChinesePrompt') : '',
    ].filter(Boolean);
  }, [intakePreview, t]);
  const addSuggestedTag = (tagName: string) => {
    const parts = tags.split(',').map(t => t.trim()).filter(Boolean);
    const selected = new Set(parts);
    selected.add(tagName);
    setTags(Array.from(selected).join(', '));
  };

  const assignImageFile = useCallback((role: UploadImageRole, file: File) => {
    if (!file.type.startsWith('image/')) {
      setSaveError(t('imageFileOnly'));
      return;
    }
    setSaveError('');
    if (role === 'result_image') {
      setResultFile(file);
    } else {
      setReferenceFile(file);
    }
    if (!title.trim()) {
      const suggestion = inferTitleFromFilename(file.name);
      if (suggestion) setTitle(suggestion);
    }
  }, [t, title]);

  const assignImageFromFiles = useCallback((role: UploadImageRole, files: FileList | File[] | null | undefined) => {
    const [firstImage] = imageFilesFromList(files);
    if (!firstImage) {
      setSaveError(t('imageFileOnly'));
      return;
    }
    assignImageFile(role, firstImage);
  }, [assignImageFile, t]);

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest('textarea, input:not([type="file"])')) {
        return;
      }
      const [clipboardImage] = imageFilesFromClipboard(event.clipboardData);
      if (!clipboardImage) return;
      event.preventDefault();
      const role: UploadImageRole = !hasExistingResultImage && !resultFile
        ? 'result_image'
        : !referenceFile
          ? 'reference_image'
          : 'result_image';
      assignImageFile(role, clipboardImage);
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [assignImageFile, hasExistingResultImage, referenceFile, resultFile]);

  const onZoneInputChange = (role: UploadImageRole) => (event: ChangeEvent<HTMLInputElement>) => {
    assignImageFromFiles(role, event.target.files);
    event.target.value = '';
  };

  const onZoneDrop = (role: UploadImageRole) => (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (role === 'result_image') {
      setResultDropActive(false);
    } else {
      setReferenceDropActive(false);
    }
    assignImageFromFiles(role, event.dataTransfer.files);
  };

  const onZoneDragOver = (role: UploadImageRole) => (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (role === 'result_image') {
      setResultDropActive(true);
    } else {
      setReferenceDropActive(true);
    }
  };

  const onZoneDragLeave = (role: UploadImageRole) => () => {
    if (role === 'result_image') {
      setResultDropActive(false);
    } else {
      setReferenceDropActive(false);
    }
  };

  const applyIntakeDraft = (draft: PromptIntakeDraft) => {
    setSaveError('');
    if (draft.title) setTitle(draft.title);
    if (draft.cluster) setCluster(draft.cluster);
    if (draft.model) setModel(draft.model);
    if (draft.author) setAuthor(draft.author);
    if (draft.sourceUrl) setSourceUrl(draft.sourceUrl);
    if (draft.tags.length > 0) setTags(draft.tags.join(', '));
    if (draft.englishPrompt) setEnglishPrompt(draft.englishPrompt);
    if (draft.traditionalChinesePrompt) setZhHantPrompt(draft.traditionalChinesePrompt);
    if (draft.simplifiedChinesePrompt) setZhHansPrompt(draft.simplifiedChinesePrompt);
    if (draft.notes) setNotes(draft.notes);
  };

  const normalizeIntakeError = (error: unknown) => {
    const detail = extractErrorDetail(error);
    if (!detail) return t('promptIntakeFetchFailed');
    if (detail === 'Please enter a valid http or https URL.') return t('promptIntakeUrlInvalid');
    if (detail === 'Failed to fetch the source URL.') return t('promptIntakeFetchBlocked');
    if (detail === 'Failed to fetch the source image.') return t('promptIntakeImageImportFailed');
    return detail;
  };

  const buildPromptIntakePreview = (text = intakeText) => {
    if (!text.trim()) {
      setIntakePreview(null);
      setIntakeFeedback({ tone: 'error', message: t('promptIntakeEmpty') });
      return null;
    }
    const draft = parsePromptIntake(text);
    if (!draft) {
      setIntakePreview(null);
      setIntakeFeedback({ tone: 'error', message: t('promptIntakeNoMatch') });
      return null;
    }
    return draft;
  };

  const previewPromptIntake = (text = intakeText) => {
    const draft = buildPromptIntakePreview(text);
    if (!draft) return false;
    setIntakePreview(draft);
    setIntakeFeedback({ tone: 'success', message: t('promptIntakePreviewReady') });
    return true;
  };

  const applyPromptIntake = (draft = intakePreview || buildPromptIntakePreview()) => {
    if (!draft) return false;
    setIntakePreview(draft);
    applyIntakeDraft(draft);
    setIntakeFeedback({ tone: 'success', message: t('promptIntakeApplied') });
    return true;
  };

  const importIntakeImageCandidate = async (candidate: CaseIntakeImageCandidate) => {
    setCandidateImageLoadingUrl(candidate.url);
    setIntakeFeedback(null);
    try {
      const imageFile = await api.fetchCaseIntakeImage(candidate.url);
      assignImageFile('reference_image', imageFile);
      setSelectedIntakeImageUrl(candidate.url);
      setIntakeFeedback({ tone: 'success', message: t('promptIntakeImageImported') });
      return true;
    } catch (error) {
      setIntakeFeedback({ tone: 'error', message: normalizeIntakeError(error) });
      return false;
    } finally {
      setCandidateImageLoadingUrl('');
    }
  };

  const fetchPromptIntake = async () => {
    if (!intakeUrl.trim()) {
      setIntakeFeedback({ tone: 'error', message: t('promptIntakeUrlEmpty') });
      return;
    }
    setIntakeLoading(true);
    setIntakeFeedback(null);
    setIntakePreview(null);
    setIntakeImageCandidates([]);
    setSelectedIntakeImageUrl('');
    setFailedIntakeImageUrls([]);
    try {
      const fetched = await api.fetchCaseIntake(intakeUrl.trim());
      setIntakeUrl(fetched.final_url);
      setIntakeText(fetched.intake_text);
      const candidates = fetched.image_candidates?.length
        ? fetched.image_candidates
        : fetched.image_url ? [{ url: fetched.image_url, source: 'page' }] : [];
      setIntakeImageCandidates(candidates);
      const draft = parsePromptIntake(fetched.intake_text);
      if (draft) {
        setIntakePreview(draft);
      }
      if (draft && candidates.length > 0) {
        setIntakeFeedback({ tone: 'success', message: t('promptIntakePreviewReadyWithImages') });
      } else if (draft) {
        setIntakeFeedback({ tone: 'success', message: t('promptIntakePreviewReady') });
      } else if (candidates.length > 0) {
        setIntakeFeedback({ tone: 'success', message: t('promptIntakeImagesReady') });
      } else {
        setIntakeFeedback({ tone: 'error', message: t('promptIntakeNoMatch') });
      }
    } catch (error) {
      setIntakeFeedback({ tone: 'error', message: normalizeIntakeError(error) });
    } finally {
      setIntakeLoading(false);
    }
  };

  const save = async () => {
    if (!title.trim() || !hasPrompt || missingRequiredImage) return;
    setSaving(true);
    setSaveError('');
    try {
      const prompts = [
        { language: 'en', text: englishPrompt.trim(), is_primary: true },
        { language: 'zh_hant', text: zhHantPrompt.trim(), is_primary: !englishPrompt.trim() },
        { language: 'zh_hans', text: zhHansPrompt.trim(), is_primary: !englishPrompt.trim() && !zhHantPrompt.trim() },
      ].filter(prompt => prompt.text);
      const payload = {
        title: title.trim(),
        model: model.trim() || undefined,
        author: author.trim() || 'User',
        source_url: sourceUrl.trim() || undefined,
        notes: notes.trim() || undefined,
        cluster_name: cluster.trim() || undefined,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        prompts,
      };
      const createdNewItem = !item;
      const saved = item ? await api.updateItem(item.id, payload) : await api.createItem(payload);
      try {
        if (resultFile) await api.uploadImage(saved.id, resultFile, 'result_image');
        if (referenceFile) await api.uploadImage(saved.id, referenceFile, 'reference_image');
      } catch (uploadError) {
        if (createdNewItem) await api.deleteItem(saved.id);
        throw uploadError;
      }
      onSaved();
      onClose();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const deleteReference = async () => {
    if (!item) return;
    if (!confirm(t('deleteReferenceConfirm'))) return;
    setDeleting(true);
    try {
      await api.deleteItem(item.id);
      onDeleted();
      onClose();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="editor modal polished-modal">
        <button className="close" onClick={onClose} aria-label={t('close')}>
          <X size={20} />
        </button>
        <div className="editor-head">
          <p className="modal-kicker">{item ? t('updateReference') : t('newReference')}</p>
          <h2>{item ? t('editPromptCard') : t('addPromptCard')}</h2>
          <p>{t('editorHelp')}</p>
        </div>

        <div className="editor-grid">
          <div className="field prompt-field intake-field">
            <span>{t('promptIntake')}</span>
            <div className="intake-url-row">
              <input
                type="url"
                placeholder={t('promptIntakeUrlPlaceholder')}
                value={intakeUrl}
                onChange={event => {
                  setIntakeUrl(event.target.value);
                  if (intakeFeedback) setIntakeFeedback(null);
                  if (intakePreview) setIntakePreview(null);
                  if (intakeImageCandidates.length > 0) setIntakeImageCandidates([]);
                  if (selectedIntakeImageUrl) setSelectedIntakeImageUrl('');
                  if (failedIntakeImageUrls.length > 0) setFailedIntakeImageUrls([]);
                }}
              />
              <button type="button" className="secondary intake-fetch-button" disabled={intakeLoading} onClick={fetchPromptIntake}>
                {intakeLoading ? t('promptIntakeFetching') : t('fetchPromptIntake')}
              </button>
            </div>
            <textarea
              className="intake-textarea"
              placeholder={t('promptIntakePlaceholder')}
              value={intakeText}
              onChange={event => {
                setIntakeText(event.target.value);
                if (intakeFeedback) setIntakeFeedback(null);
                if (intakePreview) setIntakePreview(null);
              }}
            />
            {intakePreview && (
              <div className="intake-preview" aria-label={t('promptIntakePreview')}>
                <div className="intake-preview-head">
                  <div>
                    <strong>{t('promptIntakePreview')}</strong>
                    <p>{t('promptIntakePreviewHelp')}</p>
                  </div>
                  <button type="button" className="secondary intake-apply-button" onClick={() => applyPromptIntake()}>
                    {t('promptIntakeApplyDraft')}
                  </button>
                </div>
                <div className="intake-preview-meta">
                  <span>{t('promptIntakeFieldsDetected')}: {intakePreviewFieldCount}</span>
                  {intakePreviewPromptLanguages.length > 0 && (
                    <span>{t('promptIntakePromptLanguages')}: {intakePreviewPromptLanguages.join(', ')}</span>
                  )}
                </div>
                <div className="intake-preview-grid">
                  <div className="intake-preview-card">
                    <strong>{t('title')}</strong>
                    <span>{intakePreview.title || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card">
                    <strong>{t('collection')}</strong>
                    <span>{intakePreview.cluster || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card">
                    <strong>{t('imageGeneratedFrom')}</strong>
                    <span>{intakePreview.model || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card">
                    <strong>{t('author')}</strong>
                    <span>{intakePreview.author || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card">
                    <strong>{t('sourceUrl')}</strong>
                    <span>{intakePreview.sourceUrl || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card">
                    <strong>{t('tags')}</strong>
                    <span>{intakePreview.tags.length > 0 ? intakePreview.tags.join(', ') : t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card prompt-preview-card">
                    <strong>{t('englishPrompt')}</strong>
                    <span>{intakePreview.englishPrompt || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card prompt-preview-card">
                    <strong>{t('traditionalChinesePrompt')}</strong>
                    <span>{intakePreview.traditionalChinesePrompt || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card prompt-preview-card">
                    <strong>{t('simplifiedChinesePrompt')}</strong>
                    <span>{intakePreview.simplifiedChinesePrompt || t('promptIntakeFieldEmpty')}</span>
                  </div>
                  <div className="intake-preview-card prompt-preview-card">
                    <strong>{t('notes')}</strong>
                    <span>{intakePreview.notes || t('promptIntakeFieldEmpty')}</span>
                  </div>
                </div>
              </div>
            )}
            {intakeImageCandidates.length > 0 && (
              <div className="intake-image-candidates" aria-label={t('promptIntakeImageCandidates')}>
                <div className="intake-image-candidates-head">
                  <strong>{t('promptIntakeImageCandidates')}</strong>
                  <span>{t('promptIntakeImageCandidatesHelp')}</span>
                </div>
                <div className="intake-image-candidate-grid">
                  {intakeImageCandidates.map(candidate => (
                    <button
                      type="button"
                      className={`intake-image-candidate ${selectedIntakeImageUrl === candidate.url ? 'is-selected' : ''}`}
                      key={candidate.url}
                      disabled={Boolean(candidateImageLoadingUrl)}
                      onClick={() => importIntakeImageCandidate(candidate)}
                    >
                      {failedIntakeImageUrls.includes(candidate.url) ? (
                        <div className="intake-image-fallback">{t('promptIntakeImageLoadFailed')}</div>
                      ) : (
                        <img
                          src={caseIntakeImageUrl(candidate.url)}
                          alt={candidate.alt || t('promptIntakeImageCandidateAlt')}
                          loading="lazy"
                          onError={() => setFailedIntakeImageUrls(current => current.includes(candidate.url) ? current : [...current, candidate.url])}
                        />
                      )}
                      <span>{candidateImageLoadingUrl === candidate.url ? t('promptIntakeImageImporting') : t('usePromptIntakeImage')}</span>
                      <small>{candidate.source}{candidate.url === intakeImageCandidates[0]?.url ? ` · ${t('promptIntakeImageRecommended')}` : ''}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="intake-actions">
              <p className="intake-help">{t('promptIntakeHelp')}</p>
              <div className="intake-action-buttons">
                <button type="button" className="secondary intake-button" onClick={() => previewPromptIntake()}>{t('extractPromptDraft')}</button>
                {intakePreview && (
                  <button type="button" className="secondary intake-button" onClick={() => applyPromptIntake()}>{t('promptIntakeApplyDraft')}</button>
                )}
              </div>
            </div>
            {intakeFeedback && <p className={`form-feedback ${intakeFeedback.tone}`} role="status">{intakeFeedback.message}</p>}
          </div>
          <label className="field field-title">
            <span>{t('title')}</span>
            <input placeholder={t('titlePlaceholder')} value={title} onChange={e => setTitle(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('collection')}</span>
            <input list="collection-suggestions" placeholder={t('collectionPlaceholder')} value={cluster} onChange={e => setCluster(e.target.value)} />
            <datalist id="collection-suggestions">
              {filteredClusters.map(collection => <option key={collection.id} value={collection.name} />)}
            </datalist>
          </label>
          <label className="field">
            <span>{t('imageGeneratedFrom')}</span>
            <input placeholder={t('defaultModel')} value={model} onChange={e => setModel(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('author')}</span>
            <input placeholder="User" value={author} onChange={e => setAuthor(e.target.value)} />
          </label>
          <label className="field">
            <span>{t('sourceUrl')}</span>
            <input type="url" placeholder="https://…" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} />
          </label>
          <label className="field tag-field">
            <span>{t('tags')}</span>
            <input list="tag-suggestions" placeholder={t('tagsPlaceholder')} value={tags} onChange={e => setTags(e.target.value)} />
            <datalist id="tag-suggestions">
              {filteredTags.map(tag => <option key={tag.id} value={tag.name} />)}
            </datalist>
            {filteredTags.length > 0 && (
              <div className="tag-suggestions" aria-label={t('existingTagSuggestions')}>
                {filteredTags.map(tag => <button type="button" key={tag.id} onClick={() => addSuggestedTag(tag.name)}>#{tag.name}</button>)}
              </div>
            )}
          </label>
          <label className="field prompt-field">
            <span>{t('englishPrompt')}</span>
            <textarea placeholder={t('englishPromptPlaceholder')} value={englishPrompt} onChange={e => setEnglishPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('traditionalChinesePrompt')}</span>
            <textarea placeholder={t('traditionalPromptPlaceholder')} value={zhHantPrompt} onChange={e => setZhHantPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('simplifiedChinesePrompt')}</span>
            <textarea placeholder={t('simplifiedPromptPlaceholder')} value={zhHansPrompt} onChange={e => setZhHansPrompt(e.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>{t('notes')}</span>
            <textarea placeholder={t('addNote')} value={notes} onChange={e => setNotes(e.target.value)} />
          </label>
          <label
            className={`drop-zone ${missingRequiredImage ? 'required' : ''} ${resultDropActive ? 'drag-active' : ''}`}
            onDragOver={onZoneDragOver('result_image')}
            onDragLeave={onZoneDragLeave('result_image')}
            onDrop={onZoneDrop('result_image')}
          >
            <ImagePlus size={24} />
            <strong>{resultFile ? resultFile.name : hasExistingResultImage ? t('resultImageAlreadySaved') : t('resultImageRequired')}</strong>
            <span className="drop-zone-hint">{t('imageCaptureHint')}</span>
            <span>{t('resultImageHelp')}</span>
            <input type="file" accept="image/*" required={!hasExistingResultImage} onChange={onZoneInputChange('result_image')} />
          </label>
          <label
            className={`drop-zone reference-drop-zone ${referenceDropActive ? 'drag-active' : ''}`}
            onDragOver={onZoneDragOver('reference_image')}
            onDragLeave={onZoneDragLeave('reference_image')}
            onDrop={onZoneDrop('reference_image')}
          >
            <ImagePlus size={24} />
            <strong>{referenceFile ? referenceFile.name : t('referencePhotoOptional')}</strong>
            <span className="drop-zone-hint">{t('imageCaptureHint')}</span>
            <span>{t('referencePhotoHelp')}</span>
            <input type="file" accept="image/*" onChange={onZoneInputChange('reference_image')} />
          </label>
        </div>

        {saveError && <p className="form-error" role="alert">{saveError}</p>}

        <div className="editor-actions">
          {item && <button className="danger" disabled={deleting || saving} onClick={deleteReference}><Trash2 size={16} /> {t('deleteReference')}</button>}
          <button className="secondary" onClick={onClose}>{t('cancel')}</button>
          <button className="primary" disabled={!title.trim() || !hasPrompt || missingRequiredImage || saving || deleting} onClick={save}>{saving ? t('saving') : t('saveReference')}</button>
        </div>
      </div>
    </div>
  );
}
