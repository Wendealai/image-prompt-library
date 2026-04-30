const body = ($json.body && typeof $json.body === 'object') ? $json.body : $json;
const item = body.item && typeof body.item === 'object' ? body.item : {};
const prompt = body.prompt && typeof body.prompt === 'object' ? body.prompt : {};

const itemId = String(item.id ?? '').trim();
const title = String(item.title ?? '').trim();
const modelName = String(item.model ?? '').trim();
const sourceUrl = String(item.sourceUrl ?? item.source_url ?? '').trim();
const author = String(item.author ?? '').trim();
const itemNotes = String(item.notes ?? '').trim();
const defaultImportSkillUrl = String(item.defaultImportSkillUrl ?? item.default_import_skill_url ?? '').trim();
const sourceLanguage = String(prompt.language ?? body.sourceLanguage ?? '').trim() || 'original';
const rawText = String(prompt.text ?? body.rawText ?? '').trim();
const llmModel = String(body.model ?? 'gpt-5.4-mini').trim() || 'gpt-5.4-mini';

if (!itemId) throw new Error('Missing item.id');
if (!title) throw new Error('Missing item.title');
if (!rawText) throw new Error('Missing prompt.text');

const systemPrompt = [
  'You are a prompt skeleton analyst for an image prompt library.',
  'Your job is to convert one existing prompt into a marked template for later AI-guided reuse.',
  'A case is one semantic prompt only. Ignore translation concerns.',
  'You must preserve the original prompt text exactly, character-for-character, except for wrapping editable regions with slot markers.',
  'Never translate, reorder, summarize, or rewrite any fixed skeleton text.',
  'Editable regions should cover the theme-dependent content that may need holistic coordinated rewriting later.',
  'Use this exact marker syntax: [[slot id="..." group="..." label="..." role="..." instruction="..."]]ORIGINAL TEXT[[/slot]].',
  'Slot ids must be snake_case and unique.',
  'Prefer a few meaningful slots over many tiny slots.',
  'If changing one region would require related content to change too, keep them in the same conceptual group such as theme_core, supporting_copy, or surface_detail.',
  'If a default import skill URL is provided in the user context, treat it as synced import guidance for deciding what is fixed skeleton versus editable content.',
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
  sourceUrl ? `Source URL: ${sourceUrl}` : '',
  author ? `Author: ${author}` : '',
  itemNotes ? `Item notes:\n${itemNotes}` : '',
  defaultImportSkillUrl ? `Default import skill URL: ${defaultImportSkillUrl}` : '',
  defaultImportSkillUrl ? 'Apply the synced default import skill URL above as background import guidance.' : '',
  'Original prompt:',
  rawText,
  '',
  'Return JSON only.',
].filter(Boolean).join('\n');

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
      max_output_tokens: 1400,
    },
  },
}];
