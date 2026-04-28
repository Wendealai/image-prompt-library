const inputItems = $input.all();
const expectedToken = String($env.IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN ?? '').trim();

if (!expectedToken) {
  return inputItems;
}

const configuredHeader = String($env.IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER ?? 'Authorization').trim() || 'Authorization';
const request = inputItems[0]?.json ?? {};
const headers = request.headers && typeof request.headers === 'object' ? request.headers : {};
const normalizedHeaders = Object.fromEntries(
  Object.entries(headers).map(([key, value]) => [key.toLowerCase(), Array.isArray(value) ? value[0] : value]),
);

const receivedValue = normalizedHeaders[configuredHeader.toLowerCase()];
const receivedToken = typeof receivedValue === 'string' ? receivedValue.trim() : '';
const expectedHeaderValue = configuredHeader.toLowerCase() === 'authorization'
  ? `Bearer ${expectedToken}`
  : expectedToken;

if (receivedToken !== expectedHeaderValue) {
  throw new Error('Unauthorized');
}

return inputItems;
