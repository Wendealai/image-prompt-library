const body = ($json.body && typeof $json.body === 'object') ? $json.body : $json;
const template = body.template && typeof body.template === 'object' ? body.template : {};
const slots = Array.isArray(template.slots) ? template.slots : [];
const previousVariants = Array.isArray(body.previousVariants) ? body.previousVariants : [];

const templateId = String(template.id ?? '').trim();
const itemId = String(template.itemId ?? template.item_id ?? '').trim();
const sourceLanguage = String(template.sourceLanguage ?? template.source_language ?? '').trim() || 'original';
const rawText = String(template.rawText ?? template.raw_text ?? '').trim();
const markedText = String(template.markedText ?? template.marked_text ?? '').trim();
const themeKeyword = String(body.themeKeyword ?? body.theme_keyword ?? '').trim();
const llmModel = String(body.model ?? 'gpt-5.4-mini').trim() || 'gpt-5.4-mini';

if (!templateId) throw new Error('Missing template.id');
if (!itemId) throw new Error('Missing template.itemId');
if (!markedText) throw new Error('Missing template.markedText');
if (!themeKeyword) throw new Error('Missing themeKeyword');
if (!Array.isArray(slots) || slots.length === 0) throw new Error('Template slots are required');

const normalizedSlots = slots.map((slot) => ({
  id: String(slot.id ?? '').trim(),
  group: String(slot.group ?? 'content').trim() || 'content',
  label: String(slot.label ?? slot.id ?? '').trim() || String(slot.id ?? '').trim(),
  original_text: String(slot.original_text ?? slot.originalText ?? '').trim(),
  role: String(slot.role ?? '').trim(),
  instruction: String(slot.instruction ?? '').trim(),
}));

for (const slot of normalizedSlots) {
  if (!slot.id) throw new Error('Every slot must include an id');
  if (!slot.original_text) throw new Error(`Slot ${slot.id} is missing original_text`);
}

const systemPrompt = [
  'You are a prompt remix engine for an image prompt library.',
  'You receive a marked prompt template with immutable skeleton text and editable slot regions.',
  'You must preserve the skeleton exactly and only propose new text for the provided slots.',
  'Do not return a full prompt. Return slot values only.',
  'When the user changes the theme keyword, rewrite the variable regions holistically so the whole prompt stays stylistically coherent.',
  'Different slots may need coordinated changes. Think across all slots together before responding.',
  'Never invent or remove slot ids.',
  'Return valid JSON only with keys slotValues and changeSummary.',
  'slotValues must be an array of objects with keys slot_id and text.',
  'You must include every slot exactly once.',
  'text must contain only the replacement content for that slot, without any slot markers or extra commentary.',
  'changeSummary should briefly explain the coordinated rewrite.'
].join(' ');

const slotListText = JSON.stringify(normalizedSlots, null, 2);
const previousVariantText = JSON.stringify(previousVariants.map((variant) => ({
  iteration: variant.iteration,
  renderedText: variant.renderedText ?? variant.rendered_text ?? '',
  slotValues: variant.slotValues ?? variant.slot_values ?? [],
  changeSummary: variant.changeSummary ?? variant.change_summary ?? '',
})), null, 2);

const userPrompt = [
  'Rewrite the marked prompt slots for a new theme.',
  `Template ID: ${templateId}`,
  `Item ID: ${itemId}`,
  `Source language: ${sourceLanguage}`,
  `Theme keyword: ${themeKeyword}`,
  '',
  'Marked template:',
  markedText,
  '',
  'Original prompt:',
  rawText || '(not provided)',
  '',
  'Slots:',
  slotListText,
  '',
  'Rejected / previous variants to avoid repeating too closely:',
  previousVariantText,
  '',
  'Return JSON only.',
].join('\n');

return [{
  json: {
    slotIds: normalizedSlots.map((slot) => slot.id),
    requestPayload: {
      model: llmModel,
      stream: true,
      input: [
        {
          role: 'system',
          content: [{ type: 'input_text', text: systemPrompt }],
        },
        {
          role: 'user',
          content: [{ type: 'input_text', text: userPrompt }],
        },
      ],
      text: {
        format: {
          type: 'json_object',
        },
      },
      max_output_tokens: 1600,
    },
  },
}];
