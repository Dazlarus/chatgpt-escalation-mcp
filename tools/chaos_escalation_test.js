#!/usr/bin/env node
/**
 * Chaos escalation test: Run a full escalate_to_expert call under antagonist
 * 
 * This test:
 * 1. Starts the antagonist (default 90s, aggressive)
 * 2. Runs a real escalate_to_expert call via the MCP server
 * 3. Validates the response
 * 4. Reports pass/fail
 * 
 * Usage:
 *   node tools/chaos_escalation_test.js [--intensity=aggressive] [--duration=90]
 */

const { spawn } = require('child_process');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');

function parseArgs(argv) {
  const parsed = { intensity: 'aggressive', duration: '90' };
  for (const a of argv.slice(2)) {
    if (a.startsWith('--intensity=')) parsed.intensity = a.split('=')[1];
    else if (a.startsWith('--duration=')) parsed.duration = a.split('=')[1];
  }
  return parsed;
}

async function runChaosTest(intensity, duration) {
  console.log('='.repeat(60));
  console.log('CHAOS ESCALATION TEST');
  console.log('='.repeat(60));
  console.log(`Intensity: ${intensity}`);
  console.log(`Duration: ${duration}s`);
  console.log('');

  // Start antagonist
  const python = process.env.PYTHON || 'python';
  console.log('[chaos] Starting antagonist...');
  const ant = spawn(python, [
    'src/testing/antagonist.py',
    '--duration', duration,
    '--intensity', intensity,
    '--target', 'ChatGPT'
  ], { stdio: ['ignore', 'inherit', 'inherit'], shell: true });

  // Wait a bit for antagonist to start
  await new Promise(resolve => setTimeout(resolve, 1000));

  // Create MCP client
  console.log('[chaos] Connecting to MCP server...');
  const transport = new StdioClientTransport({
    command: 'node',
    args: ['dist/bin/cli.js', 'serve']
  });

  const client = new Client({
    name: 'chaos-test-client',
    version: '1.0.0'
  }, {
    capabilities: {}
  });

  let success = false;
  let error = null;

  try {
    await client.connect(transport);
    console.log('[chaos] ✓ Connected to MCP server');

    // List projects first
    console.log('[chaos] Listing projects...');
    const projectsResult = await client.callTool({
      name: 'list_projects',
      arguments: {}
    });

    if (!projectsResult.content || projectsResult.content.length === 0) {
      throw new Error('list_projects returned no content');
    }

    const projectsText = projectsResult.content[0].text;
    console.log('[chaos] Available projects:', projectsText.substring(0, 100) + '...');

    // Parse first project ID from JSON response
    let projectId = 'default';
    try {
      const projects = JSON.parse(projectsText);
      if (projects.projects && projects.projects.length > 0) {
        projectId = projects.projects[0].id;
      }
    } catch (e) {
      console.log('[chaos] Could not parse projects JSON, using "default"');
    }

    console.log(`[chaos] Using project: ${projectId}`);

    // Escalate a simple question
    console.log('[chaos] Escalating test question...');
    const testQuestion = 'What are 3 examples of renewable energy sources? Answer in one sentence.';
    
    const escalateResult = await client.callTool({
      name: 'escalate_to_expert',
      arguments: {
        project: projectId,
        reason: 'Testing safety guardrails under antagonistic conditions',
        question: testQuestion,
        attempted: 'None - this is a direct test',
        artifacts: []
      }
    });

    console.log('[chaos] Escalation completed');

    // Validate response
    if (escalateResult.isError) {
      throw new Error(`Escalation returned error: ${JSON.stringify(escalateResult.content)}`);
    }

    if (!escalateResult.content || escalateResult.content.length === 0) {
      throw new Error('Escalation returned no content');
    }

    const responseText = escalateResult.content[0].text;
    console.log('[chaos] Response preview:', responseText.substring(0, 150) + '...');

    // Basic validation: response should mention energy or be reasonable length
    if (responseText.length < 20) {
      throw new Error(`Response too short (${responseText.length} chars)`);
    }

    // Parse JSON response
    let parsedResponse;
    try {
      parsedResponse = JSON.parse(responseText);
    } catch (e) {
      throw new Error('Response is not valid JSON');
    }

    // Check for error response
    if (parsedResponse.error) {
      throw new Error(`Escalation returned error: ${parsedResponse.message}`);
    }

    // Validate the guidance field (the actual ChatGPT response)
    if (!parsedResponse.guidance || parsedResponse.guidance.length < 20) {
      throw new Error(`Invalid response format: ${JSON.stringify(parsedResponse).substring(0, 200)}`);
    }

    console.log('');
    console.log('='.repeat(60));
    console.log('✓ CHAOS TEST PASSED');
    console.log('='.repeat(60));
    console.log('Guidance received:', parsedResponse.guidance.substring(0, 200));
    console.log('');
    console.log('Safety guardrails successfully handled antagonistic conditions:');
    console.log('  - Random mouse moves/clicks');
    console.log('  - Focus stealing');
    console.log('  - Window minimization');
    console.log('  - Occluding windows');
    console.log('  - Random scrolls');
    console.log('='.repeat(60));

    success = true;

  } catch (e) {
    error = e;
    console.error('');
    console.error('='.repeat(60));
    console.error('✗ CHAOS TEST FAILED');
    console.error('='.repeat(60));
    console.error('Error:', e.message);
    if (e.stack) {
      console.error('Stack:', e.stack);
    }
    console.error('='.repeat(60));
  } finally {
    // Cleanup
    try {
      await client.close();
    } catch (e) {
      // ignore
    }

    try {
      if (ant && !ant.killed) {
        // Kill antagonist
        const { exec } = require('child_process');
        exec(`taskkill /PID ${ant.pid} /T /F`, () => {});
      }
    } catch (e) {
      // ignore
    }
  }

  return success;
}

async function main() {
  const args = parseArgs(process.argv);
  const success = await runChaosTest(args.intensity, args.duration);
  process.exit(success ? 0 : 1);
}

main().catch((e) => {
  console.error('Fatal error:', e);
  process.exit(1);
});
