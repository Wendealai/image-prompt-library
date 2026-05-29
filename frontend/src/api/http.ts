function summarizeResponseError(body: string, status: number) {
  const trimmed = body.trim();
  if (!trimmed) return `Request failed with status ${status}.`;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: string; message?: string };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim();
    if (typeof parsed.message === 'string' && parsed.message.trim()) return parsed.message.trim();
  } catch {
  }
  if (/^<!doctype html/i.test(trimmed) || /^<html/i.test(trimmed)) return `Request failed with status ${status}.`;
  return trimmed;
}

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string) {
    super(summarizeResponseError(body, status));
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: 'same-origin', headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  return r.json();
}

export async function fileFromUrl(url: string, init?: RequestInit): Promise<File> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(await r.text());
  const blob = await r.blob();
  const filename = r.headers.get('x-intake-filename') || 'reference-image';
  return new File([blob], filename, { type: blob.type || 'image/png' });
}
