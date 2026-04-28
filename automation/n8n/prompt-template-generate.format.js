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
    if (trimmed.startsWith('data:')) dataLines.push(trimmed.slice(5).trim());
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

const parsedTextObjects = textCandidates.map((item) => safeParseLoose(item)).filter((item) => item && typeof item === 'object');
const allObjects = [source, ...objectCandidates, ...parsedTextObjects].filter((item) => item && typeof item === 'object');

const readByPath = (payload, path) => {
  let cursor = payload;
  for (const segment of path) {
    if (!cursor || typeof cursor !== 'object') return undefined;
    cursor = cursor[segment];
  }
  return cursor;
};

let slotValues = null;
let changeSummary = '';
for (const candidate of allObjects) {
  const nextSlotValues = readByPath(candidate, ['slotValues']) ?? readByPath(candidate, ['slot_values']) ?? readByPath(candidate, ['data', 'slotValues']) ?? readByPath(candidate, ['result', 'slotValues']);
  if (!slotValues && Array.isArray(nextSlotValues)) slotValues = nextSlotValues;
  if (!changeSummary) {
    const nextSummary = readByPath(candidate, ['changeSummary']) ?? readByPath(candidate, ['change_summary']) ?? readByPath(candidate, ['notes']) ?? readByPath(candidate, ['data', 'changeSummary']);
    if (typeof nextSummary === 'string' && nextSummary.trim()) changeSummary = nextSummary.trim();
  }
}

if (!slotValues) {
  throw new Error('Workflow returned no slotValues array.');
}

const normalizedSlotValues = slotValues.map((value) => {
  const slotId = String(value.slot_id ?? value.slotId ?? '').trim();
  const text = String(value.text ?? '').trim();
  if (!slotId) throw new Error('Each slot value must include slot_id.');
  if (!text) throw new Error(`Slot ${slotId} is missing replacement text.`);
  return { slot_id: slotId, text };
});

const expectedSlotIds = $item(0).$node['Prepare Prompt Template Generate Payload'].json.slotIds;
const seenIds = new Set();
for (const value of normalizedSlotValues) {
  if (seenIds.has(value.slot_id)) throw new Error(`Duplicate slot_id: ${value.slot_id}`);
  seenIds.add(value.slot_id);
}
for (const expectedId of expectedSlotIds) {
  if (!seenIds.has(expectedId)) throw new Error(`Missing slot value for ${expectedId}`);
}
if (normalizedSlotValues.length !== expectedSlotIds.length) {
  throw new Error('Workflow returned an unexpected number of slot values.');
}

return [{
  json: {
    slotValues: normalizedSlotValues,
    changeSummary,
  },
}];
