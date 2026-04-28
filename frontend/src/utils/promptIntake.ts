export interface PromptIntakeDraft {
  title?: string;
  model?: string;
  author?: string;
  sourceUrl?: string;
  cluster?: string;
  tags: string[];
  englishPrompt?: string;
  traditionalChinesePrompt?: string;
  simplifiedChinesePrompt?: string;
  notes?: string;
}

type DraftSectionKey =
  | 'title'
  | 'model'
  | 'author'
  | 'sourceUrl'
  | 'cluster'
  | 'tags'
  | 'englishPrompt'
  | 'traditionalChinesePrompt'
  | 'simplifiedChinesePrompt'
  | 'genericPrompt'
  | 'notes';

type DraftState = PromptIntakeDraft;

const INLINE_PATTERNS: Array<{ key: DraftSectionKey; pattern: RegExp }> = [
  { key: 'title', pattern: /^(?:title|name|標題|标题)\s*[:：-]\s*(.+)$/i },
  { key: 'cluster', pattern: /^(?:collection|cluster|category|group|類別|类别|分類|分类|主題|主题)\s*[:：-]\s*(.+)$/i },
  { key: 'tags', pattern: /^(?:tags?|hashtags?|標籤|标签)\s*[:：-]\s*(.+)$/i },
  { key: 'sourceUrl', pattern: /^(?:source(?:\s+url)?|url|link|來源(?:\s*url)?|来源(?:\s*url)?|網址|网址)\s*[:：-]\s*(.+)$/i },
  { key: 'model', pattern: /^(?:model|tool|engine|模型|工具)\s*[:：-]\s*(.+)$/i },
  { key: 'author', pattern: /^(?:author|creator|作者)\s*[:：-]\s*(.+)$/i },
  { key: 'notes', pattern: /^(?:notes?|memo|備註|备注|說明|说明)\s*[:：-]\s*(.+)$/i },
  { key: 'englishPrompt', pattern: /^(?:english(?:\s+prompt)?|en(?:\s+prompt)?|prompt\s*\(en\)|英文(?:\s*prompt|\s*提示詞|\s*提示词)?)\s*[:：-]\s*(.+)$/i },
  { key: 'traditionalChinesePrompt', pattern: /^(?:(?:traditional|繁體|繁体)(?:\s+chinese)?(?:\s+prompt)?|zh[-_\s]?hant|prompt\s*\(zh[-_\s]?hant\)|繁中(?:\s*prompt|\s*提示詞|\s*提示词)?)\s*[:：-]\s*(.+)$/i },
  { key: 'simplifiedChinesePrompt', pattern: /^(?:(?:simplified|簡體|简体)(?:\s+chinese)?(?:\s+prompt)?|zh[-_\s]?hans|prompt\s*\(zh[-_\s]?hans\)|简中(?:\s*prompt|\s*提示詞|\s*提示词)?)\s*[:：-]\s*(.+)$/i },
  { key: 'genericPrompt', pattern: /^(?:prompt|提示詞|提示词)\s*[:：-]\s*(.+)$/i },
];

const HEADING_ALIASES: Record<DraftSectionKey, string[]> = {
  title: ['title', 'name', '標題', '标题'],
  model: ['model', 'tool', 'engine', '模型', '工具'],
  author: ['author', 'creator', '作者'],
  sourceUrl: ['source', 'source url', 'url', 'link', '來源', '来源', '來源 url', '来源 url', '網址', '网址'],
  cluster: ['collection', 'cluster', 'category', 'group', '類別', '类别', '分類', '分类', '主題', '主题'],
  tags: ['tag', 'tags', 'hashtag', 'hashtags', '標籤', '标签'],
  englishPrompt: ['english prompt', 'english', 'en prompt', 'prompt en', 'prompt english', '英文 prompt', '英文提示詞', '英文提示词'],
  traditionalChinesePrompt: ['traditional chinese prompt', 'traditional chinese', 'zh hant', 'zh_hant', 'zh-hant', '繁體中文 prompt', '繁体中文 prompt', '繁中 prompt', '繁體 prompt', '繁体 prompt'],
  simplifiedChinesePrompt: ['simplified chinese prompt', 'simplified chinese', 'zh hans', 'zh_hans', 'zh-hans', '簡體中文 prompt', '简体中文 prompt', '简中 prompt', '簡中 prompt', '簡體 prompt', '简体 prompt'],
  genericPrompt: ['prompt', '提示詞', '提示词'],
  notes: ['notes', 'note', 'memo', '備註', '备注', '說明', '说明'],
};

const URL_PATTERN = /https?:\/\/[^\s<>"')\]]+/i;
const CJK_PATTERN = /[\u3400-\u9fff]/;
const SIMPLIFIED_ONLY_CHARS = new Set('汉气龙画广门风体国云梦灯宝东车鸟创图术层网艺书发观台区'.split(''));
const TRADITIONAL_ONLY_CHARS = new Set('漢氣龍畫廣門風體國雲夢燈寶東車鳥創圖術層網藝書發觀臺區'.split(''));

function stripLineDecorators(line: string): string {
  return line
    .replace(/^\s*[>#*\-]+\s*/, '')
    .replace(/^\s*\d+\.\s*/, '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .trim();
}

function normalizeHeading(line: string): string {
  return stripLineDecorators(line)
    .replace(/[：:]+$/, '')
    .replace(/[()[\]{}]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function normalizeBlock(value: string): string {
  return value
    .replace(/\r/g, '')
    .split('\n')
    .map(line => line.trimEnd())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function normalizeSingleLine(value: string): string {
  return normalizeBlock(value).replace(/\s+/g, ' ').trim();
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized) continue;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(normalized);
  }
  return result;
}

function parseTags(value: string): string[] {
  const hashtags = Array.from(value.matchAll(/(^|\s)#([A-Za-z0-9][\w-]{1,39})/g)).map(match => match[2]);
  const inline = value
    .replace(/#/g, '')
    .split(/[,\n，、;/|]+/)
    .map(part => part.trim().replace(/^["']|["']$/g, ''))
    .filter(part => part && part.length <= 48);
  return dedupe([...inline, ...hashtags]);
}

function extractHashtags(value: string): string[] {
  return dedupe(Array.from(value.matchAll(/(^|\s)#([A-Za-z0-9][\w-]{1,39})/g)).map(match => match[2]));
}

function containsAnyChar(text: string, chars: Set<string>): boolean {
  for (const char of text) {
    if (chars.has(char)) return true;
  }
  return false;
}

function inferPromptField(text: string): 'englishPrompt' | 'traditionalChinesePrompt' | 'simplifiedChinesePrompt' {
  if (containsAnyChar(text, SIMPLIFIED_ONLY_CHARS)) return 'simplifiedChinesePrompt';
  if (containsAnyChar(text, TRADITIONAL_ONLY_CHARS)) return 'traditionalChinesePrompt';
  if (!CJK_PATTERN.test(text)) return 'englishPrompt';
  const latinCount = (text.match(/[A-Za-z]/g) || []).length;
  const cjkCount = (text.match(/[\u3400-\u9fff]/g) || []).length;
  if (latinCount > 0 && latinCount >= cjkCount) return 'englishPrompt';
  return 'traditionalChinesePrompt';
}

function firstUrl(value: string): string | undefined {
  return value.match(URL_PATTERN)?.[0];
}

function appendBlock(existing: string | undefined, next: string): string {
  return existing ? `${existing}\n\n${next}` : next;
}

function applyScalar(draft: DraftState, key: 'title' | 'model' | 'author' | 'sourceUrl' | 'cluster' | 'notes', value: string): void {
  const cleaned = key === 'sourceUrl' ? firstUrl(value) || normalizeSingleLine(value) : normalizeBlock(value);
  if (!cleaned) return;
  if (key === 'notes') {
    draft.notes = appendBlock(draft.notes, cleaned);
    return;
  }
  draft[key] = normalizeSingleLine(cleaned);
}

function assignSectionValue(draft: DraftState, key: DraftSectionKey, value: string): void {
  const cleaned = normalizeBlock(value);
  if (!cleaned) return;
  if (key === 'tags') {
    draft.tags = dedupe([...draft.tags, ...parseTags(cleaned)]);
    return;
  }
  if (key === 'genericPrompt') {
    assignSectionValue(draft, inferPromptField(cleaned), cleaned);
    return;
  }
  if (key === 'englishPrompt' || key === 'traditionalChinesePrompt' || key === 'simplifiedChinesePrompt') {
    draft[key] = appendBlock(draft[key], cleaned);
    return;
  }
  applyScalar(draft, key, cleaned);
}

function detectSection(line: string): { key: DraftSectionKey; inlineValue?: string } | null {
  const cleanedLine = stripLineDecorators(line);
  for (const entry of INLINE_PATTERNS) {
    const match = cleanedLine.match(entry.pattern);
    if (match) return { key: entry.key, inlineValue: match[1] };
  }
  const normalizedHeading = normalizeHeading(cleanedLine);
  if (!normalizedHeading) return null;
  for (const [key, aliases] of Object.entries(HEADING_ALIASES) as Array<[DraftSectionKey, string[]]>) {
    if (aliases.includes(normalizedHeading)) return { key };
  }
  return null;
}

function inferTitle(lines: string[]): string | undefined {
  for (const line of lines) {
    const cleaned = normalizeSingleLine(stripLineDecorators(line));
    if (!cleaned) continue;
    if (URL_PATTERN.test(cleaned)) continue;
    if (cleaned.startsWith('#')) continue;
    if (cleaned.length > 120) continue;
    return cleaned;
  }
  return undefined;
}

function hasAnyParsedField(draft: PromptIntakeDraft): boolean {
  return Boolean(
    draft.title
    || draft.model
    || draft.author
    || draft.sourceUrl
    || draft.cluster
    || draft.notes
    || draft.tags.length > 0
    || draft.englishPrompt
    || draft.traditionalChinesePrompt
    || draft.simplifiedChinesePrompt,
  );
}

export function parsePromptIntake(input: string): PromptIntakeDraft | null {
  const text = input.replace(/\r/g, '').trim();
  if (!text) return null;

  const draft: PromptIntakeDraft = { tags: [] };
  const looseLines: string[] = [];
  let activeSection: DraftSectionKey | null = null;
  let activeLines: string[] = [];

  const flushActiveSection = () => {
    if (!activeSection || activeLines.length === 0) {
      activeSection = null;
      activeLines = [];
      return;
    }
    assignSectionValue(draft, activeSection, activeLines.join('\n'));
    activeSection = null;
    activeLines = [];
  };

  for (const rawLine of text.split('\n')) {
    const detected = detectSection(rawLine);
    if (detected) {
      flushActiveSection();
      if (detected.inlineValue) assignSectionValue(draft, detected.key, detected.inlineValue);
      else activeSection = detected.key;
      continue;
    }
    if (activeSection) activeLines.push(rawLine);
    else looseLines.push(rawLine);
  }

  flushActiveSection();

  if (!draft.sourceUrl) draft.sourceUrl = firstUrl(text);
  if (draft.tags.length === 0) draft.tags = extractHashtags(text);
  if (!draft.title) draft.title = inferTitle(looseLines);

  return hasAnyParsedField(draft) ? draft : null;
}
