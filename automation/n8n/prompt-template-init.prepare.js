const body = ($json.body && typeof $json.body === 'object') ? $json.body : $json;
const item = body.item && typeof body.item === 'object' ? body.item : {};
const prompt = body.prompt && typeof body.prompt === 'object' ? body.prompt : {};

const itemId = String(item.id ?? '').trim();
const title = String(item.title ?? '').trim();
const modelName = String(item.model ?? '').trim();
const sourceLanguage = String(prompt.language ?? body.sourceLanguage ?? '').trim() || 'original';
const rawText = String(prompt.text ?? body.rawText ?? '').trim();
const llmModel = String(body.model ?? 'gpt-5.4-mini').trim() || 'gpt-5.4-mini';
const promptStartMarker = '<<<IMAGE_PROMPT_BEGIN>>>';
const promptEndMarker = '<<<IMAGE_PROMPT_END>>>';

if (!itemId) throw new Error('Missing item.id');
if (!title) throw new Error('Missing item.title');
if (!rawText) throw new Error('Missing prompt.text');

const systemPrompt = [
  'You are a prompt skeleton analyst for an image prompt library.',
  'Your job is to convert one existing prompt into a marked template for later AI-guided reuse.',
  'A case is one semantic prompt only. Ignore translation concerns.',
  'The user message will include the original prompt between explicit start and end markers.',
  'Only the text between those markers belongs to the original prompt.',
  'Do not include the boundary markers or any follow-up instructions in markedText.',
  'You must preserve the original prompt text exactly, character-for-character, except for wrapping editable regions with slot markers.',
  'Never translate, reorder, summarize, or rewrite any fixed skeleton text.',
  'Editable regions should cover the theme-dependent content that may need holistic coordinated rewriting later.',
  'Use this exact marker syntax: [[slot id="..." group="..." label="..." role="..." instruction="..."]]ORIGINAL TEXT[[/slot]].',
  'Slots must be flat top-level spans only.',
  'Never nest one slot inside another slot.',
  'Never create overlapping slots.',
  'Slot ids must be snake_case and unique.',
  'Prefer a few meaningful slots over many tiny slots.',
  'If changing one region would require related content to change too, keep them in the same conceptual group such as theme_core, supporting_copy, or surface_detail.',
  'Return valid JSON only with keys markedText, confidence, notes, and sourceLanguage.',
  'confidence must be a number between 0 and 1.',
  'notes should briefly explain the skeleton/variable split.',
  'markedText must render back to the exact original prompt when the slot markers are removed.',
  'There must be at least one slot.'
].join(' ');

const userPrompt = [
  'Analyze this prompt and mark only the editable regions.',
  `Item ID: ${itemId}`,
  `Title: ${title}`,
  `Model: ${modelName || 'unknown'}`,
  `Source language: ${sourceLanguage}`,
  'Original prompt follows between these exact markers:',
  promptStartMarker,
  rawText,
  promptEndMarker,
  '',
  'Only mark text that appears between those markers.',
  'Do not include the markers themselves in markedText.',
  'Return JSON only.',
].join('\n');

return [{
  json: {
    rawText,
    sourceLanguage,
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
      temperature: 0,
      max_output_tokens: 1400,
    },
  },
}];
