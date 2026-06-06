type SavePickerWindow = Window & typeof globalThis & {
  showSaveFilePicker?: (options?: {
    suggestedName?: string;
    excludeAcceptAllOption?: boolean;
    types?: Array<{
      description?: string;
      accept: Record<string, string[]>;
    }>;
  }) => Promise<{
    createWritable: () => Promise<{
      write: (data: Blob) => Promise<void>;
      close: () => Promise<void>;
    }>;
  }>;
};

function mimeTypeToExtension(mimeType: string) {
  switch (mimeType.toLowerCase()) {
    case 'image/png':
      return '.png';
    case 'image/webp':
      return '.webp';
    case 'image/gif':
      return '.gif';
    case 'image/jpeg':
      return '.jpg';
    default:
      return '.bin';
  }
}

export async function downloadBlobFromUrl(href: string, filename: string) {
  const response = await fetch(href, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const savePickerWindow = window as SavePickerWindow;
  if (typeof savePickerWindow.showSaveFilePicker === 'function') {
    const mimeType = blob.type || 'application/octet-stream';
    const handle = await savePickerWindow.showSaveFilePicker({
      suggestedName: filename,
      types: [{
        description: mimeType,
        accept: { [mimeType]: [mimeTypeToExtension(mimeType)] },
      }],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.rel = 'noopener';
  link.style.display = 'none';
  document.body.appendChild(link);
  window.requestAnimationFrame(() => {
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  });
}
