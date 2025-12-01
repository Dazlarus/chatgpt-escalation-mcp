#!/usr/bin/env node
const { createRequire } = require('module');
const requirePkg = createRequire(__filename);
const { Client } = requirePkg('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = requirePkg('@modelcontextprotocol/sdk/client/stdio.js');

function log(...args) { console.log(...args); }
function fail(msg) { console.error(msg); process.exit(1); }

async function main() {
  const transport = new StdioClientTransport({
    command: 'node',
    args: ['dist/bin/cli.js', 'serve'],
    stderr: 'pipe',
  });

  const client = new Client({ name: 'protocol-probe', version: '0.0.1' });
  client.registerCapabilities({ tools: {} });

  // bubble server stderr
  if (transport.stderr) {
    transport.stderr.on('data', (chunk) => process.stderr.write(chunk.toString()));
  }

  await client.connect(transport);
  log('[probe] Connected');

  // List tools and validate presence
  const { tools } = await client.listTools({}, { timeout: 600000 });
  const toolNames = tools.map(t => t.name);
  log('[probe] Tools:', toolNames);
  if (!toolNames.includes('list_projects') || !toolNames.includes('escalate_to_expert')) {
    fail('[probe] Missing required tools in server');
  }

  // Validate schemas (best-effort)
  const escalateTool = tools.find(t => t.name === 'escalate_to_expert');
  if (!escalateTool || !escalateTool.inputSchema) {
    fail('[probe] escalate_to_expert missing inputSchema');
  }
  const sch = escalateTool.inputSchema;
  const props = sch.properties || {};
  if (!props.project || props.project.type !== 'string') {
    fail('[probe] schema: project:string missing/invalid');
  }
  if (!props.question || props.question.type !== 'string') {
    fail('[probe] schema: question:string missing/invalid');
  }
  // reason may be optional

  // Call list_projects and parse JSON
  const listRes = await client.callTool({ name: 'list_projects', params: {} }, undefined, { timeout: 600000 });
  if (!Array.isArray(listRes.content) || listRes.content.length === 0 || listRes.content[0].type !== 'text') {
    fail('[probe] list_projects returned unexpected content');
  }
  let listJson;
  try { listJson = JSON.parse(listRes.content[0].text); }
  catch (e) { fail('[probe] list_projects text not valid JSON'); }
  if (!Array.isArray(listJson.available_projects) || listJson.available_projects.length === 0) {
    fail('[probe] list_projects: available_projects missing/empty');
  }
  const defaultProj = listJson.available_projects.find(p => p.id === 'default');
  if (!defaultProj) {
    fail('[probe] list_projects: default project not found');
  }
  log('[probe] Projects OK');

  // Call escalate_to_expert with minimal valid payload
  log('[probe] Calling escalate_to_expert...');
  const escRes = await client.callTool({
    name: 'escalate_to_expert',
    arguments: {
      project: 'default',
      reason: 'Protocol compliance probe',
      question: 'Please return a valid structured JSON payload to confirm MCP compliance.'
    }
  }, undefined, { timeout: 600000 });

  if (escRes.isError === true) {
    fail('[probe] escalate_to_expert returned isError=true');
  }

  if (!Array.isArray(escRes.content) || escRes.content.length === 0 || escRes.content[0].type !== 'text') {
    fail('[probe] escalate_to_expert returned unexpected content');
  }

  let escText = escRes.content[0].text;
  let escJson;
  try { escJson = JSON.parse(escText); }
  catch (e) { fail('[probe] escalate_to_expert text not valid JSON'); }

  if (escJson.error === true) {
    fail('[probe] escalate_to_expert returned error JSON: ' + (escJson.message || 'unknown'));
  }

  // Validate structured response fields
  if (typeof escJson.guidance !== 'string') {
    fail('[probe] escalate_to_expert: guidance missing or not string');
  }
  if (!Array.isArray(escJson.action_plan)) {
    fail('[probe] escalate_to_expert: action_plan missing or not array');
  }
  if (typeof escJson.priority !== 'string') {
    fail('[probe] escalate_to_expert: priority missing or not string');
  }
  log('[probe] Escalation response OK');

  await client.close();
  log('[probe] SUCCESS');
}

main().catch(err => fail('[probe] Error: ' + (err && err.message || err)));
