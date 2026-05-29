import { useCallback, useEffect, useState } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import type { UploadImageRole } from '../types';
import type { Translator } from '../utils/i18n';

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

export function useEditorImageInputs({
  t,
  title,
  setTitle,
  setSaveError,
  hasExistingResultImage,
}: {
  t: Translator;
  title: string;
  setTitle: (title: string) => void;
  setSaveError: (message: string) => void;
  hasExistingResultImage: boolean;
}) {
  const [resultFile, setResultFile] = useState<File>();
  const [referenceFile, setReferenceFile] = useState<File>();
  const [resultDropActive, setResultDropActive] = useState(false);
  const [referenceDropActive, setReferenceDropActive] = useState(false);

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
  }, [setSaveError, setTitle, t, title]);

  const assignImageFromFiles = useCallback((role: UploadImageRole, files: FileList | File[] | null | undefined) => {
    const [firstImage] = imageFilesFromList(files);
    if (!firstImage) {
      setSaveError(t('imageFileOnly'));
      return;
    }
    assignImageFile(role, firstImage);
  }, [assignImageFile, setSaveError, t]);

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

  return {
    resultFile,
    referenceFile,
    resultDropActive,
    referenceDropActive,
    assignImageFile,
    onZoneInputChange,
    onZoneDrop,
    onZoneDragOver,
    onZoneDragLeave,
  };
}
