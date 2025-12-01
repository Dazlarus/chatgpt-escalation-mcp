import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import type {
  ExpertBackend,
  EscalationPacket,
  ExpertResponse,
  AppConfig,
  DriverCommand,
  DriverResult,
} from "../types.js";
import { getLogger } from "../util/logging.js";
import { buildPrompt, extractJson, validateExpertResponse } from "../util/promptBuilder.js";
import { getProjectConversation, getProjectFolder } from "../util/configLoader.js";

const logger = getLogger("chatgpt-desktop");

// Mutex for sequential operations
let operationMutex: Promise<void> = Promise.resolve();

/**
 * Acquire mutex for sequential operations
 */
function withMutex<T>(fn: () => Promise<T>): Promise<T> {
  const previous = operationMutex;
  let releaseMutex: () => void;

  operationMutex = new Promise((resolve) => {
    releaseMutex = resolve;
  });

  return previous.then(async () => {
    try {
      return await fn();
    } finally {
      releaseMutex!();
    }
  });
}

/**
 * Get the path to the driver script for the current platform
 */
function getDriverPath(platform: "win" | "mac"): string {
  // Try multiple locations for the driver
  // Use process.cwd() and known paths relative to package root
  const scriptName = platform === "win" ? "driver_robust.py" : "driver.scpt";
  
  const possiblePaths = [
    // From package root (when running via npx or npm or from dist/bin/cli.js)
    path.join(process.cwd(), "src", "drivers", platform, scriptName),
    path.join(process.cwd(), "drivers", platform, scriptName),
    // From compiled dist/ when running as dist/bin/cli.js or dist/src/server.js
    path.join(__dirname, "..", "..", "src", "drivers", platform, scriptName),
    path.join(__dirname, "..", "..", "..", "src", "drivers", platform, scriptName),
    // From node_modules installation
    path.join(__dirname, "..", "drivers", platform, scriptName),
    path.join(__dirname, "..", "..", "drivers", platform, scriptName),
  ];

  for (const p of possiblePaths) {
    if (fs.existsSync(p)) {
      return p;
    }
  }

  throw new Error(`Driver not found for platform: ${platform}. Searched: ${possiblePaths.join(", ")}`);
}

/**
 * Execute a driver command on Windows using Python
 */
async function executeWindowsDriver(command: DriverCommand): Promise<DriverResult> {
  const driverPath = getDriverPath("win");
  logger.debug("Executing Windows driver", { command: command.action, driverPath });

  return new Promise((resolve) => {
    const python = spawn("python", [driverPath], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    python.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    python.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    python.on("close", (code) => {
      if (code !== 0) {
        logger.error("Python driver exited with error", { code, stderr });
        resolve({ success: false, error: stderr || `Exit code: ${code}` });
        return;
      }

      try {
        const result = JSON.parse(stdout.trim());
        resolve(result);
      } catch (e) {
        logger.error("Failed to parse driver response", { stdout, error: e });
        resolve({ success: false, error: `Invalid response: ${stdout}` });
      }
    });

    python.on("error", (err) => {
      logger.error("Failed to spawn Python driver", { error: err });
      resolve({ success: false, error: `Failed to run driver: ${err.message}` });
    });

    // Send command to stdin
    python.stdin.write(JSON.stringify(command));
    python.stdin.end();
  });
}

/**
 * Execute a driver command on macOS using AppleScript
 */
async function executeMacDriver(command: DriverCommand): Promise<DriverResult> {
  const driverPath = getDriverPath("mac");
  logger.debug("Executing macOS driver", { command: command.action, driverPath });

  return new Promise((resolve) => {
    const osascript = spawn("osascript", [driverPath, JSON.stringify(command)]);

    let stdout = "";
    let stderr = "";

    osascript.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    osascript.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    osascript.on("close", (code) => {
      if (code !== 0) {
        logger.error("AppleScript driver exited with error", { code, stderr });
        resolve({ success: false, error: stderr || `Exit code: ${code}` });
        return;
      }

      try {
        const result = JSON.parse(stdout.trim());
        resolve(result);
      } catch (e) {
        logger.error("Failed to parse driver response", { stdout, error: e });
        resolve({ success: false, error: `Invalid response: ${stdout}` });
      }
    });

    osascript.on("error", (err) => {
      logger.error("Failed to spawn AppleScript driver", { error: err });
      resolve({ success: false, error: `Failed to run driver: ${err.message}` });
    });
  });
}

/**
 * Execute a driver command based on platform
 */
async function executeDriver(
  platform: "win" | "mac",
  command: DriverCommand
): Promise<DriverResult> {
  if (platform === "win") {
    return executeWindowsDriver(command);
  } else {
    return executeMacDriver(command);
  }
}

/**
 * Send an escalation to ChatGPT Desktop
 */
async function sendEscalation(
  packet: EscalationPacket,
  config: AppConfig
): Promise<ExpertResponse> {
  return withMutex(async () => {
    const { platform, responseTimeout } = config.chatgpt;
    logger.info("Sending escalation via ChatGPT Desktop", {
      project: packet.project,
      platform,
    });

    // Step 1: Check ChatGPT is available
    const checkResult = await executeDriver(platform, { action: "check_chatgpt" });
    if (!checkResult.success) {
      throw new Error(`ChatGPT Desktop check failed: ${checkResult.error}`);
    }
    
    const checkData = checkResult.data as { found: boolean; message?: string };
    if (!checkData.found) {
      throw new Error(checkData.message || "ChatGPT Desktop not found. Please open the application.");
    }
    logger.debug("ChatGPT Desktop found");

    // Build prompt
    const prompt = buildPrompt(packet);
    logger.debug("Built prompt", { length: prompt.length });

    // Run escalate flow in the driver in a single call. This avoids creating multiple ephemeral driver
    // processes which start/stop ChatGPT repeatedly and cause the UI to be unstable.
    const conversationTitle = getProjectConversation(config, packet.project);
    if (!conversationTitle) {
      throw new Error(`No conversation configured for project: ${packet.project}`);
    }
    const projectFolder = getProjectFolder(config, packet.project);

    const escalateResult = await executeDriver(platform, {
      action: "escalate",
      params: {
        project_name: projectFolder || undefined,
        conversation: conversationTitle,
        message: prompt,
        timeout_ms: responseTimeout,
      },
    });
    if (!escalateResult.success) {
      throw new Error(`Escalation failed: ${escalateResult.error}`);
    }
    logger.debug("Escalation completed", { project: packet.project, conversation: conversationTitle });

    const getResult = escalateResult;

    const responseData = getResult.data as { response: string };
    const rawResponse = responseData.response;
    logger.debug("Got raw response", { length: rawResponse.length });

    // Step 7: Parse JSON response
    const jsonText = extractJson(rawResponse);
    let parsed: unknown;

    try {
      parsed = JSON.parse(jsonText);
    } catch (error) {
      logger.error("Failed to parse JSON response", { jsonText, error });
      throw new Error(`Failed to parse ChatGPT response as JSON: ${error}`);
    }

    // Step 8: Validate response
    if (!validateExpertResponse(parsed)) {
      logger.error("Invalid response format", { parsed });
      throw new Error("ChatGPT response does not match expected format");
    }

    logger.info("Escalation completed successfully");
    return parsed;
  });
}

/**
 * Check if ChatGPT Desktop is available
 */
async function checkAvailability(
  config: AppConfig
): Promise<{ available: boolean; message: string }> {
  const { platform } = config.chatgpt;

  try {
    const result = await executeDriver(platform, { action: "check_chatgpt" });

    if (!result.success) {
      return { available: false, message: result.error || "Driver error" };
    }

    const data = result.data as { found: boolean; message?: string };
    return {
      available: data.found,
      message: data.found
        ? "ChatGPT Desktop is running"
        : data.message || "ChatGPT Desktop not found",
    };
  } catch (error) {
    return {
      available: false,
      message: `Error checking ChatGPT: ${error}`,
    };
  }
}

/**
 * Send a raw message (for testing, bypasses escalation format)
 */
async function sendRawMessage(
  message: string,
  projectId: string,
  config: AppConfig
): Promise<string> {
  return withMutex(async () => {
    const { platform, responseTimeout } = config.chatgpt;
    logger.info("Sending raw message via ChatGPT Desktop", { projectId, platform });

    // Step 1: Check ChatGPT is available
    const checkResult = await executeDriver(platform, { action: "check_chatgpt" });
    if (!checkResult.success) {
      throw new Error(`ChatGPT Desktop check failed: ${checkResult.error}`);
    }
    
    const checkData = checkResult.data as { found: boolean; message?: string };
    if (!checkData.found) {
      throw new Error(checkData.message || "ChatGPT Desktop not found. Please open the application.");
    }

    // Step 2: Focus ChatGPT window
    const focusResult = await executeDriver(platform, { action: "focus_chatgpt" });
    if (!focusResult.success) {
      throw new Error(`Failed to focus ChatGPT: ${focusResult.error}`);
    }

    // Step 3: Find the project conversation
    const conversationTitle = getProjectConversation(config, projectId);
    if (!conversationTitle) {
      throw new Error(`No conversation configured for project: ${projectId}`);
    }

    // Get optional project folder for vision-based navigation
    const projectFolder = getProjectFolder(config, projectId);

    const findResult = await executeDriver(platform, {
      action: "find_conversation",
      params: { 
        title: conversationTitle,
        project_name: projectFolder || undefined
      },
    });
    if (!findResult.success) {
      throw new Error(`Failed to find conversation "${conversationTitle}": ${findResult.error}`);
    }

    // Step 4: Send the message directly
    const sendResult = await executeDriver(platform, {
      action: "send_message",
      params: { message },
    });
    if (!sendResult.success) {
      throw new Error(`Failed to send message: ${sendResult.error}`);
    }

    // Step 5: Wait for response
    const waitResult = await executeDriver(platform, {
      action: "wait_for_response",
      params: { timeout_ms: responseTimeout },
    });
    if (!waitResult.success) {
      throw new Error(`Timeout waiting for response: ${waitResult.error}`);
    }

    // Step 6: Get the response
    const getResult = await executeDriver(platform, { action: "get_last_response" });
    if (!getResult.success) {
      throw new Error(`Failed to get response: ${getResult.error}`);
    }

    const responseData = getResult.data as { response: string };
    return responseData.response;
  });
}

/**
 * Cleanup (no-op for desktop backend)
 */
async function cleanup(): Promise<void> {
  logger.debug("Cleanup called (no-op for desktop backend)");
}

/**
 * Create the ChatGPT Desktop backend
 */
export function createChatGPTDesktopBackend(config: AppConfig): ExpertBackend & {
  sendRawMessage: (message: string, projectId: string) => Promise<string>;
} {
  return {
    name: "chatgpt-desktop",
    sendEscalation: (packet: EscalationPacket) => sendEscalation(packet, config),
    checkAvailability: () => checkAvailability(config),
    cleanup,
    sendRawMessage: (message: string, projectId: string) => sendRawMessage(message, projectId, config),
  };
}

/**
 * Check if Python and required packages are available (Windows only)
 */
export async function checkPythonDependencies(): Promise<{
  available: boolean;
  message: string;
}> {
  return new Promise((resolve) => {
    const python = spawn("python", ["-c", "import pywinauto; import pyperclip; print('ok')"]);

    let stdout = "";
    let stderr = "";

    python.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    python.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    python.on("close", (code) => {
      if (code === 0 && stdout.trim() === "ok") {
        resolve({ available: true, message: "Python dependencies available" });
      } else {
        resolve({
          available: false,
          message: `Missing Python dependencies. Run: pip install pywinauto pyperclip\n${stderr}`,
        });
      }
    });

    python.on("error", () => {
      resolve({
        available: false,
        message: "Python not found. Please install Python 3.x",
      });
    });
  });
}
