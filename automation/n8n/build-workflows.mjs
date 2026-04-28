import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const asxsCredential = {
  openAiApi: {
    id: 'WwKQlbKl3pE8swBl',
    name: 'ASXS',
  },
};

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, relativePath), 'utf8');
}

function write(relativePath, data) {
  fs.writeFileSync(path.join(__dirname, relativePath), `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

function webhookNode({ name, pathName, position }) {
  return {
    id: `${pathName}_webhook`,
    name,
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2,
    position,
    parameters: {
      path: pathName,
      httpMethod: 'POST',
      responseMode: 'lastNode',
      options: {},
    },
    webhookId: pathName,
  };
}

function codeNode({ name, code, position }) {
  return {
    id: `${name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
    name,
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position,
    parameters: {
      jsCode: code,
    },
  };
}

function authNode({ name, position }) {
  return codeNode({
    name,
    code: read('prompt-template-auth-gate.js'),
    position,
  });
}

function httpNode({ name, position }) {
  return {
    id: `${name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
    name,
    type: 'n8n-nodes-base.httpRequest',
    typeVersion: 4.2,
    position,
    parameters: {
      method: 'POST',
      url: 'https://api.asxs.top/v1/responses',
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: '={{$json.requestPayload}}',
      responseFormat: 'string',
      options: {
        timeout: 120000,
      },
      authentication: 'predefinedCredentialType',
      nodeCredentialType: 'openAiApi',
    },
    continueOnFail: true,
    retryOnFail: true,
    maxTries: 4,
    waitBetweenTries: 3000,
    credentials: asxsCredential,
  };
}

function makeConnections(sequence) {
  const connections = {};
  for (let index = 0; index < sequence.length - 1; index += 1) {
    connections[sequence[index].name] = {
      main: [[{ node: sequence[index + 1].name, type: 'main', index: 0 }]],
    };
  }
  return connections;
}

const initNodes = [
  webhookNode({ name: 'Webhook Prompt Template Init', pathName: 'image-prompt-library-template-init', position: [-640, 80] }),
  authNode({ name: 'Authorize Prompt Template Init Request', position: [-500, 80] }),
  codeNode({ name: 'Prepare Prompt Template Init Payload', code: read('prompt-template-init.prepare.js'), position: [-360, 80] }),
  httpNode({ name: 'Call ASXS Responses For Template Init', position: [-60, 80] }),
  codeNode({ name: 'Format Prompt Template Init Output', code: read('prompt-template-init.format.js'), position: [240, 80] }),
];

const generateNodes = [
  webhookNode({ name: 'Webhook Prompt Template Generate', pathName: 'image-prompt-library-template-generate', position: [-640, 80] }),
  authNode({ name: 'Authorize Prompt Template Generate Request', position: [-500, 80] }),
  codeNode({ name: 'Prepare Prompt Template Generate Payload', code: read('prompt-template-generate.prepare.js'), position: [-360, 80] }),
  httpNode({ name: 'Call ASXS Responses For Template Generate', position: [-60, 80] }),
  codeNode({ name: 'Format Prompt Template Generate Output', code: read('prompt-template-generate.format.js'), position: [240, 80] }),
];

write('prompt-template-init.workflow.json', {
  name: 'Image Prompt Library - Template Init',
  settings: {
    executionOrder: 'v1',
  },
  nodes: initNodes,
  connections: makeConnections(initNodes),
});

write('prompt-template-generate.workflow.json', {
  name: 'Image Prompt Library - Template Generate',
  settings: {
    executionOrder: 'v1',
  },
  nodes: generateNodes,
  connections: makeConnections(generateNodes),
});
