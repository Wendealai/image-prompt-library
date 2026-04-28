import type { PromptGenerationVariantRecord, PromptRenderSegment, PromptTemplateSlot } from '../types';

const SLOT_PATTERN = /\[\[slot(?<attrs>[^\]]*)\]\](?<content>.*?)\[\[\/slot\]\]/gs;
const ATTR_PATTERN = /([a-zA-Z_][\w-]*)="([^"]*)"/g;

function parseAttrs(rawAttrs: string) {
  return Array.from(rawAttrs.matchAll(ATTR_PATTERN)).reduce<Record<string, string>>((acc, match) => {
    const [, key, value] = match;
    acc[key] = value;
    return acc;
  }, {});
}

export function buildSlotValueRecord(slots: PromptTemplateSlot[], variant?: PromptGenerationVariantRecord | null) {
  const nextValues = Object.fromEntries(slots.map(slot => [slot.id, slot.original_text])) as Record<string, string>;
  for (const value of variant?.slot_values || []) {
    if (value.slot_id in nextValues) nextValues[value.slot_id] = value.text;
  }
  return nextValues;
}

export function renderMarkedPrompt(markedText: string, slotValues: Record<string, string>) {
  const renderedParts: string[] = [];
  const segments: PromptRenderSegment[] = [];
  let cursor = 0;

  for (const match of markedText.matchAll(SLOT_PATTERN)) {
    const startIndex = match.index ?? 0;
    const attrs = parseAttrs(match.groups?.attrs || '');
    const slotId = attrs.id || '';
    const originalText = match.groups?.content || '';
    const fixedText = markedText.slice(cursor, startIndex);

    if (fixedText) {
      renderedParts.push(fixedText);
      segments.push({ type: 'fixed', text: fixedText, changed: false });
    }

    const rawNextText = slotValues[slotId];
    const nextText = rawNextText === '' || rawNextText === undefined ? originalText : rawNextText;
    renderedParts.push(nextText);
    segments.push({
      type: 'slot',
      text: nextText,
      changed: nextText !== originalText,
      slot_id: slotId || undefined,
      label: attrs.label || slotId || undefined,
      group: attrs.group || undefined,
      before: originalText,
    });
    cursor = startIndex + match[0].length;
  }

  const tailText = markedText.slice(cursor);
  if (tailText) {
    renderedParts.push(tailText);
    segments.push({ type: 'fixed', text: tailText, changed: false });
  }

  return {
    renderedText: renderedParts.join(''),
    segments,
  };
}
