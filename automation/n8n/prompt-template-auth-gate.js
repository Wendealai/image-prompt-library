const inputItems = $input.all();
const expectedToken = __WORKFLOW_TOKEN__;

if (!expectedToken) {
  return inputItems;
}

const configuredHeader = __WORKFLOW_TOKEN_HEADER__;
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
