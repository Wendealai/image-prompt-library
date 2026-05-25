const source = $json;

const raw = typeof source.body === 'string'
  ? source.body
  : typeof source.data === 'string'
    ? source.data
    : typeof source === 'string'
      ? source
      : JSON.stringify(source);

if (typeof source.statusCode === 'number' && source.statusCode >= 400) {
  throw new Error(raw.slice(0, 2000));
}

const safeParseLoose = (value) => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  const normalized = trimmed
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim();
  if (!(normalized.startsWith('{') || normalized.startsWith('['))) return value;
  try {
    return JSON.parse(normalized);
  } catch {
    return value;
  }
};

const textCandidates = [];
const objectCandidates = [];
const seenText = new Set();
let deltaBuffer = '';

const pushText = (value) => {
  if (typeof value !== 'string') return;
  const text = value.trim();
  if (!text || seenText.has(text)) return;
  seenText.add(text);
  textCandidates.push(text);
};

const pushObject = (value) => {
  if (!value || typeof value !== 'object') return;
  objectCandidates.push(value);
};

const walk = (node) => {
  if (!node) return;
  if (typeof node === 'string') {
    const parsed = safeParseLoose(node);
    if (parsed !== node) {
      walk(parsed);
      return;
    }
    pushText(node);
    return;
  }
  if (Array.isArray(node)) {
    node.forEach(walk);
    return;
  }
  if (typeof node !== 'object') return;

  pushObject(node);

  const nodeType = typeof node.type === 'string' ? node.type : '';
  const nodeEvent = typeof node.event === 'string' ? node.event : '';
  if (typeof node.delta === 'string' && /output_text\.delta$/i.test(nodeType || nodeEvent || '')) {
    deltaBuffer += node.delta;
  }
  if (typeof node.text === 'string' && /output_text\.done$/i.test(nodeType || nodeEvent || '')) {
    pushText(node.text);
  }
  if (node.part && typeof node.part === 'object' && typeof node.part.text === 'string') {
    pushText(node.part.text);
  }
  if (typeof node.output_text === 'string') {
    pushText(node.output_text);
  }
  if (Array.isArray(node.output_text)) {
    for (const chunk of node.output_text) {
      if (typeof chunk === 'string') pushText(chunk);
      else if (chunk && typeof chunk === 'object' && typeof chunk.text === 'string') pushText(chunk.text);
    }
  }

  for (const [key, value] of Object.entries(node)) {
    if (key === 'delta' || key === 'text' || key === 'output_text') continue;
    walk(value);
  }
};

const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
const blocks = normalized.split('\n\n').map((item) => item.trim()).filter(Boolean);
let parsedSse = false;
for (const block of blocks) {
  const lines = block.split('\n');
  const dataLines = [];
  let eventType = '';
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(':')) continue;
    if (trimmed.startsWith('event:')) {
      eventType = trimmed.slice(6).trim();
      continue;
    }
    if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice(5).trim());
    }
  }
  if (dataLines.length === 0) continue;
  parsedSse = true;
  const merged = dataLines.join('\n').trim();
  if (!merged || merged === '[DONE]') continue;
  try {
    const payload = JSON.parse(merged);
    if (eventType && (!payload.type || typeof payload.type !== 'string')) payload.type = eventType;
    walk(payload);
  } catch {
    pushText(merged);
  }
}

if (!parsedSse) walk(safeParseLoose(normalized));
if (deltaBuffer.trim()) pushText(deltaBuffer);

const parsedTextObjects = textCandidates
  .map((item) => safeParseLoose(item))
  .filter((item) => item && typeof item === 'object');
const allObjects = [source, ...objectCandidates, ...parsedTextObjects].filter((item) => item && typeof item === 'object');

const readByPath = (payload, path) => {
  let cursor = payload;
  for (const segment of path) {
    if (!cursor || typeof cursor !== 'object') return '';
    cursor = cursor[segment];
  }
  return typeof cursor === 'string' ? cursor.trim() : cursor;
};

const firstString = (paths) => {
  for (const candidate of allObjects) {
    for (const path of paths) {
      const value = readByPath(candidate, path);
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
  }
  return '';
};

const firstNumber = (paths) => {
  for (const candidate of allObjects) {
    for (const path of paths) {
      const value = readByPath(candidate, path);
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (typeof value === 'string' && value.trim()) {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
      }
    }
  }
  return null;
};

let markedText = firstString([
  ['markedText'],
  ['marked_text'],
  ['data', 'markedText'],
  ['data', 'marked_text'],
  ['result', 'markedText'],
]);

const notes = firstString([
  ['notes'],
  ['summary'],
  ['data', 'notes'],
  ['data', 'summary'],
  ['result', 'notes'],
]);

const sourceLanguage = firstString([
  ['sourceLanguage'],
  ['source_language'],
  ['data', 'sourceLanguage'],
  ['result', 'sourceLanguage'],
]) || $item(0).$node['Prepare Prompt Template Init Payload'].json.sourceLanguage;

const confidenceRaw = firstNumber([
  ['confidence'],
  ['data', 'confidence'],
  ['result', 'confidence'],
]);
const confidence = confidenceRaw === null ? null : Math.max(0, Math.min(1, confidenceRaw));

if (!markedText) {
  throw new Error('Workflow returned no markedText.');
}

const stripSlotMarkup = (input) => input.replace(/\[\[slot[^\]]*\]\](.*?)\[\[\/slot\]\]/gs, '$1');
const rawText = $item(0).$node['Prepare Prompt Template Init Payload'].json.rawText;
const removePromptScaffolding = (input) => {
  let cleaned = input
    .replace(/^<<<IMAGE_PROMPT_BEGIN>>>\n?/i, '')
    .replace(/\n?<<<IMAGE_PROMPT_END>>>\s*$/i, '')
    .trim();

  const trailingInstructions = [
    'Only mark text that appears between those markers.',
    'Do not include the markers themselves in markedText.',
    'Return JSON only.',
  ];

  for (const instruction of trailingInstructions) {
    const escaped = instruction.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    cleaned = cleaned.replace(new RegExp(`\\n+${escaped}\\s*$`, 'i'), '').trimEnd();
  }

  return cleaned.trim();
};

let rendered = stripSlotMarkup(markedText);
if (rendered !== rawText) {
  const cleanedMarkedText = removePromptScaffolding(markedText);
  const cleanedRendered = stripSlotMarkup(cleanedMarkedText);
  if (cleanedRendered === rawText) {
    markedText = cleanedMarkedText;
    rendered = cleanedRendered;
  }
}

if (rendered !== rawText) {
  throw new Error('markedText does not render back to the original prompt exactly.');
}
if (!/\[\[slot[^\]]*\]\].*?\[\[\/slot\]\]/s.test(markedText)) {
  throw new Error('markedText must contain at least one slot marker.');
}

return [{
  json: {
    markedText,
    confidence,
    notes,
    sourceLanguage,
  },
}];
