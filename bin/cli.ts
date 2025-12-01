#!/usr/bin/env node

import { Command } from "commander";
import * as readline from "readline";
import * as os from "os";
import {
  loadConfig,
  saveConfig,
  validateConfig,
  getConfigSummary,
  getConfigDir,
  getConfigPath,
  initConfigDir,
  configExists,
  detectPlatform,
} from "../src/util/configLoader.js";
import { initializeLogger, getLogger } from "../src/util/logging.js";
import {
  createChatGPTDesktopBackend,
  checkPythonDependencies,
} from "../src/backends/chatgpt-desktop.js";
import { runServer } from "../src/server.js";
import { buildTestPrompt } from "../src/util/promptBuilder.js";
import type { AppConfig, Platform } from "../src/types.js";

const program = new Command();

// Colors for terminal output
const colors = {
  reset: "\x1b[0m",
  bright: "\x1b[1m",
  dim: "\x1b[2m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
};

function success(msg: string): void {
  console.log(`${colors.green}✓${colors.reset} ${msg}`);
}

function error(msg: string): void {
  console.error(`${colors.red}✗${colors.reset} ${msg}`);
}

function warn(msg: string): void {
  console.log(`${colors.yellow}⚠${colors.reset} ${msg}`);
}

function info(msg: string): void {
  console.log(`${colors.blue}ℹ${colors.reset} ${msg}`);
}

function heading(msg: string): void {
  console.log(`\n${colors.bright}${colors.cyan}${msg}${colors.reset}\n`);
}

/**
 * Simple prompt helper
 */
function prompt(question: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    rl.question(question, (answer: string) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

/**
 * Init command - Setup wizard
 */
async function initCommand(): Promise<void> {
  heading("ChatGPT Desktop Escalation MCP Server - Setup Wizard");

  // Initialize config directory
  initConfigDir();
  info(`Config directory: ${getConfigDir()}`);

  // Check for existing config
  if (configExists()) {
    const answer = await prompt(
      "Configuration already exists. Overwrite? (y/N): "
    );
    if (answer.toLowerCase() !== "y") {
      info("Setup cancelled. Existing configuration preserved.");
      return;
    }
  }

  // Step 1: Detect/confirm platform
  heading("Step 1: Platform Detection");

  const detectedPlatform = detectPlatform();
  console.log(`Detected platform: ${detectedPlatform === "win" ? "Windows" : "macOS"}`);

  const platformAnswer = await prompt(
    `Use detected platform? (Y/n, or type 'win' or 'mac'): `
  );

  let platform: Platform = detectedPlatform;
  if (platformAnswer.toLowerCase() === "win") {
    platform = "win";
  } else if (platformAnswer.toLowerCase() === "mac") {
    platform = "mac";
  } else if (platformAnswer.toLowerCase() === "n") {
    platform = detectedPlatform === "win" ? "mac" : "win";
  }

  success(`Platform set to: ${platform === "win" ? "Windows" : "macOS"}`);

  // Step 2: Check dependencies
  heading("Step 2: Check Dependencies");

  if (platform === "win") {
    info("Checking Python dependencies...");
    const pythonCheck = await checkPythonDependencies();
    if (pythonCheck.available) {
      success(pythonCheck.message);
    } else {
      error(pythonCheck.message);
      console.log(`
${colors.yellow}To install required Python packages:${colors.reset}
  pip install pywinauto pyperclip

Then run this command again.
`);
      const continueAnyway = await prompt("Continue anyway? (y/N): ");
      if (continueAnyway.toLowerCase() !== "y") {
        return;
      }
    }
  } else {
    info("macOS uses built-in AppleScript - no additional dependencies needed.");
    success("Dependencies OK");
  }

  // Step 3: Set up project conversations
  heading("Step 3: Configure Project Conversations");

  console.log(`
${colors.bright}How This Works:${colors.reset}

The escalation tool will automatically navigate to specific ChatGPT
conversations based on the project you're working on.

For each project, you need to:
1. Open ChatGPT Desktop
2. Create a new conversation (or use an existing one)
3. Give it a memorable, unique title
4. Tell us the exact title here

The tool will search for conversations by title in the sidebar.
`);

  const projects: Record<string, string> = {};

  // Always set up a global project first
  info('Setting up "global" project (used as default)...');

  console.log(`
Create a conversation in ChatGPT Desktop for general escalations.
Name it something like "Roo Expert Help" or "Agent Supervisor"
`);

  const globalTitle = await prompt('Conversation title for "global": ');
  if (globalTitle) {
    projects["global"] = globalTitle;
    success("Global project configured!");
  } else {
    warn("No title provided for global project. You'll need to configure this later.");
  }

  // Add more projects
  let addMore = true;
  while (addMore) {
    const answer = await prompt("\nAdd another project? (y/N): ");
    if (answer.toLowerCase() !== "y") {
      addMore = false;
      continue;
    }

    const projectId = await prompt("Project ID (e.g., 'my-app', 'backend'): ");
    if (!projectId) {
      warn("No project ID provided, skipping.");
      continue;
    }

    const projectTitle = await prompt(
      `Conversation title for '${projectId}': `
    );
    if (projectTitle) {
      projects[projectId] = projectTitle;
      success(`Project '${projectId}' configured!`);
    } else {
      warn(`No title provided for '${projectId}', skipping.`);
    }
  }

  // Save configuration
  const finalConfig: AppConfig = {
    chatgpt: {
      platform,
      responseTimeout: 120000,
      projects,
    },
    logging: {
      level: "info",
    },
  };

  saveConfig(finalConfig);

  // Step 4: Show integration instructions
  heading("Step 4: Integrate with Your Agent");

  console.log(`
${colors.bright}Configuration saved!${colors.reset}

To use with ${colors.cyan}Roo Code${colors.reset}, add to ${colors.dim}.roo/mcp.json${colors.reset}:

${colors.dim}----------------------------------------${colors.reset}
{
  "mcpServers": {
    "chatgpt-escalation": {
      "type": "stdio",
      "command": "npx",
      "args": ["chatgpt-escalation-mcp", "serve"]
    }
  }
}
${colors.dim}----------------------------------------${colors.reset}

To use with ${colors.cyan}GitHub Copilot${colors.reset}, add to ${colors.dim}.vscode/mcp.json${colors.reset}:

${colors.dim}----------------------------------------${colors.reset}
{
  "servers": {
    "chatgpt-escalation": {
      "type": "stdio",
      "command": "npx",
      "args": ["chatgpt-escalation-mcp", "serve"]
    }
  }
}
${colors.dim}----------------------------------------${colors.reset}

${colors.bright}Important:${colors.reset} Tell your agent in its instructions:

  "When you are stuck or unsure after trying reasonable steps,
   call the MCP tool escalate_to_expert."
`);

  success("Setup complete!");
  info(`Run 'chatgpt-escalation-mcp doctor' to verify your setup.`);
}

/**
 * Serve command - Run MCP server
 */
async function serveCommand(): Promise<void> {
  await runServer();
}

/**
 * Doctor command - Validate setup
 */
async function doctorCommand(): Promise<void> {
  heading("ChatGPT Desktop Escalation MCP Server - Health Check");

  initializeLogger("info");
  const logger = getLogger("doctor");

  let hasErrors = false;

  // Check 1: Config file exists
  info("Checking configuration...");

  if (!configExists()) {
    error(`Configuration not found at ${getConfigPath()}`);
    info("Run 'chatgpt-escalation-mcp init' to set up.");
    process.exit(1);
  }

  success("Configuration file found");

  // Check 2: Load and validate config
  const config = loadConfig();
  const validation = validateConfig(config);

  if (validation.errors.length > 0) {
    error("Configuration errors:");
    validation.errors.forEach((e) => console.log(`  - ${e}`));
    hasErrors = true;
  } else {
    success("Configuration is valid");
  }

  if (validation.warnings.length > 0) {
    warn("Configuration warnings:");
    validation.warnings.forEach((w) => console.log(`  - ${w}`));
  }

  console.log(`\n${getConfigSummary(config)}\n`);

  // Check 3: Platform-specific dependencies
  info(`Checking ${config.chatgpt.platform === "win" ? "Windows" : "macOS"} dependencies...`);

  if (config.chatgpt.platform === "win") {
    const pythonCheck = await checkPythonDependencies();
    if (pythonCheck.available) {
      success(pythonCheck.message);
    } else {
      error(pythonCheck.message);
      hasErrors = true;
    }
  } else {
    success("macOS AppleScript is built-in");
  }

  // Check 4: Test ChatGPT Desktop availability
  info("Checking ChatGPT Desktop availability...");

  try {
    const backend = createChatGPTDesktopBackend(config);
    const availability = await backend.checkAvailability();

    if (availability.available) {
      success(availability.message);
    } else {
      warn(availability.message);
      console.log("  Make sure ChatGPT Desktop is open and running.");
    }
  } catch (err) {
    error(`ChatGPT check failed: ${err}`);
    hasErrors = true;
  }

  // Summary
  heading("Summary");

  if (!hasErrors && validation.valid) {
    success("All checks passed! Your setup is ready.");
    console.log(`
${colors.dim}Next steps:${colors.reset}
1. Make sure ChatGPT Desktop is open
2. Verify your conversation titles exist in the sidebar
3. Test with: chatgpt-escalation-mcp test --project global
`);
  } else {
    error("Some checks failed. Please fix the issues above.");
    process.exit(1);
  }
}

/**
 * Test command - Send a test message
 */
async function testCommand(question: string | undefined, options: { project: string; raw: boolean }): Promise<void> {
  heading("ChatGPT Desktop Escalation MCP Server - Test");

  initializeLogger("info");
  const logger = getLogger("test");

  const projectId = options.project || "global";
  const useRawMode = options.raw || !!question;
  info(`Testing project: ${projectId}`);
  if (useRawMode) {
    info("Mode: Raw message (no escalation format)");
  } else {
    info("Mode: Full escalation format");
  }

  // Load config
  const config = loadConfig();
  const validation = validateConfig(config);

  if (!validation.valid) {
    error("Invalid configuration. Run 'chatgpt-escalation-mcp doctor' for details.");
    process.exit(1);
  }

  // Check project exists
  if (!config.chatgpt.projects[projectId]) {
    error(`Project '${projectId}' not found in configuration.`);
    info(`Available projects: ${Object.keys(config.chatgpt.projects).join(", ")}`);
    process.exit(1);
  }

  const conversationTitle = config.chatgpt.projects[projectId];
  info(`Conversation title: "${conversationTitle}"`);

  // Create backend and test
  info("Connecting to ChatGPT Desktop...");

  const backend = createChatGPTDesktopBackend(config);

  try {
    // Check availability first
    const availability = await backend.checkAvailability();
    if (!availability.available) {
      error(availability.message);
      info("Please open ChatGPT Desktop and try again.");
      process.exit(1);
    }
    success("ChatGPT Desktop found");

    info("Sending test message...");
    warn("This will send a message to ChatGPT. Press Ctrl+C to cancel.");
    
    await new Promise((resolve) => setTimeout(resolve, 3000));

    if (useRawMode) {
      // Raw mode - send message directly without escalation format
      const testMessage = question || "Hello! Please respond with: TEST SUCCESSFUL";
      info(`Sending: "${testMessage.substring(0, 50)}${testMessage.length > 50 ? '...' : ''}"`);  
      
      const response = await backend.sendRawMessage(testMessage, projectId);
      
      success("Test completed!");
      console.log("\n" + colors.bright + "Response:" + colors.reset);
      console.log(response);
    } else {
      // Full escalation mode
      const response = await backend.sendEscalation({
        project: projectId,
        reason: "Testing the escalation MCP tool",
        question: "This is a simple test of the escalation system. Please respond with a brief acknowledgment.",
      });

      success("Test completed!");
      console.log("\n" + colors.bright + "Response (parsed JSON):" + colors.reset);
      console.log(JSON.stringify(response, null, 2));
    }
  } catch (err) {
    error(`Test failed: ${err}`);
    process.exit(1);
  } finally {
    await backend.cleanup();
  }
}

// Configure CLI
program
  .name("chatgpt-escalation-mcp")
  .description("MCP server for escalating questions to ChatGPT Desktop")
  .version("1.0.0");

program
  .command("init")
  .description("Initialize with an interactive setup wizard")
  .action(initCommand);

program
  .command("serve")
  .description("Run the MCP server (stdio transport)")
  .action(serveCommand);

program
  .command("doctor")
  .description("Validate configuration and check dependencies")
  .action(doctorCommand);

program
  .command("test [question]")
  .description("Send a test message to verify end-to-end functionality")
  .option("-p, --project <id>", "Project ID to test", "global")
  .option("-r, --raw", "Send raw message without escalation format")
  .action(testCommand);

// Parse and run
program.parse();
