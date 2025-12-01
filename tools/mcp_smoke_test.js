#!/usr/bin/env node
const { createRequire } = require('module');
const requirePkg = createRequire(__filename);
const { Client } = requirePkg('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = requirePkg('@modelcontextprotocol/sdk/client/stdio.js');

async function run() {
  // Spawn the server via CLI 'serve' command for stdio transport
  const transport = new StdioClientTransport({
    command: 'node',
    args: ['dist/bin/cli.js', 'serve'],
    stderr: 'pipe',
  });

  const client = new Client({ name: 'smoke-test', version: '0.0.1' });

  client.registerCapabilities({ tools: {} });

  try {
    // Attach stderr handler to surface server logs
    const stderr = transport.stderr;
    if (stderr) {
      stderr.on('data', (chunk) => process.stderr.write(chunk.toString()));
    }
    await client.connect(transport);
    console.log('Connected to server');

    // List tools
    const tools = await client.listTools({}, { timeout: 600000 });
    console.log('Tools:', tools.tools.map(t => t.name));

    // Call list_projects
    const listProjectsResult = await client.callTool({ name: 'list_projects', params: {} }, undefined, { timeout: 600000 });
    console.log('list_projects result:', listProjectsResult);

    // If default project exists, test escalate_to_expert in raw mode by sending test.
    // The server will perform backend check and may fail if conversation not found.
    if (listProjectsResult && listProjectsResult.content) {
      console.log('Sending escalate_to_expert smoke test (dry)');
      try {
        const escalateResult = await client.callTool({
          name: 'escalate_to_expert',
          arguments: {
            project: 'default',
            reason: 'smoke test',
            question: 'Please confirm the escalation test is working (reply OK).',
          },
        }, undefined, { timeout: 600000 });
        console.log('escalate_to_expert result:', escalateResult);
      } catch (err) {
        console.error('escalate_to_expert error (expected if conv not found):', err.message || err);
      }
    }

    await client.close();
    console.log('Disconnected');
  } catch (err) {
    console.error('Error during smokes test:', err);
    process.exit(1);
  }
}

run();
