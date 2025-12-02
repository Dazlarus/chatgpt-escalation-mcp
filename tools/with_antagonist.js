#!/usr/bin/env node
// Run a command while an antagonist process runs in parallel
// Usage:
//   node tools/with_antagonist.js --duration=60 --intensity=medium -- <command to run>

const { spawn, exec } = require('child_process');

function parseArgs(argv) {
  const idx = argv.indexOf('--');
  const opts = idx === -1 ? argv.slice(2) : argv.slice(2, idx);
  const cmd = idx === -1 ? [] : argv.slice(idx + 1);
  const parsed = { duration: '60', intensity: 'medium', target: 'ChatGPT', seed: undefined };
  for (const a of opts) {
    if (a.startsWith('--duration=')) parsed.duration = a.split('=')[1];
    else if (a.startsWith('--intensity=')) parsed.intensity = a.split('=')[1];
    else if (a.startsWith('--target=')) parsed.target = a.split('=')[1];
    else if (a.startsWith('--seed=')) parsed.seed = a.split('=')[1];
  }
  return { parsed, cmd };
}

function taskkill(pid) {
  return new Promise((resolve) => {
    exec(`taskkill /PID ${pid} /T /F`, () => resolve());
  });
}

async function main() {
  const { parsed, cmd } = parseArgs(process.argv);
  if (cmd.length === 0) {
    console.error('[with_antagonist] No command provided after --');
    process.exit(1);
  }

  const python = process.env.PYTHON || 'python';
  const antagonistArgs = [
    'src/testing/antagonist.py',
    `--duration`, parsed.duration,
    `--intensity`, parsed.intensity,
    `--target`, parsed.target,
  ];
  if (parsed.seed) antagonistArgs.push('--seed', parsed.seed);

  console.log(`[with_antagonist] starting antagonist for ${parsed.duration}s (intensity=${parsed.intensity})`);
  const ant = spawn(python, antagonistArgs, { stdio: ['ignore', 'inherit', 'inherit'], shell: true });

  console.log(`[with_antagonist] running command: ${cmd.join(' ')}`);
  const child = spawn(cmd.join(' '), { stdio: 'inherit', shell: true });

  let exiting = false;
  function cleanup() {
    if (exiting) return;
    exiting = true;
    if (ant && !ant.killed) {
      taskkill(ant.pid).then(() => process.exit(child.exitCode ?? 0));
    } else {
      process.exit(child.exitCode ?? 0);
    }
  }

  child.on('exit', cleanup);
  child.on('error', (err) => { console.error('[with_antagonist] command error:', err); cleanup(); });

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
}

main().catch((e) => { console.error(e); process.exit(1); });
