import type { EscalationPacket, EscalationArtifact } from "../types.js";

/**
 * Format artifacts into a readable string for the prompt
 */
function formatArtifacts(artifacts?: EscalationArtifact[]): string {
  if (!artifacts || artifacts.length === 0) {
    return "None provided";
  }

  return artifacts
    .map((artifact, index) => {
      const label = artifact.pathOrLabel || `Artifact ${index + 1}`;
      const typeLabel = artifact.type.replace("_", " ").toUpperCase();
      return `--- [${typeLabel}] ${label} ---\n${artifact.content}\n---`;
    })
    .join("\n\n");
}

/**
 * Build the full escalation prompt to send to ChatGPT
 */
export function buildPrompt(packet: EscalationPacket): string {
  const systemInstructions = `You are the expert supervisor of an autonomous coding agent named Roo Code.

An agent is escalating a question to you. Your job is to provide clear, actionable guidance.

IMPORTANT: You MUST respond ONLY with valid JSON in the following exact format, with no additional text before or after:

{
  "guidance": "Your main guidance and explanation here",
  "action_plan": ["Step 1", "Step 2", "Step 3"],
  "priority": "low|medium|high",
  "notes_for_user": "Optional notes for the human developer if needed"
}

Rules:
- "guidance" must be a string with your main advice
- "action_plan" must be an array of strings, each being a concrete action step
- "priority" must be exactly one of: "low", "medium", or "high"
- "notes_for_user" is optional, include only if there's something the human should know
- Do NOT include any text outside the JSON object
- Do NOT wrap the JSON in markdown code blocks`;

  const escalationDetails = `
═══════════════════════════════════════════════════════════════════════════════
ESCALATION REQUEST
═══════════════════════════════════════════════════════════════════════════════

REASON FOR ESCALATION:
${packet.reason}

SPECIFIC QUESTION:
${packet.question}

WHAT THE AGENT HAS ALREADY TRIED:
${packet.attempted || "Not specified"}

PROJECT CONTEXT:
${packet.projectContext || "Not specified"}

ATTACHED ARTIFACTS:
${formatArtifacts(packet.artifacts)}

═══════════════════════════════════════════════════════════════════════════════
`;

  return `${systemInstructions}\n${escalationDetails}`;
}

/**
 * Build a simple test prompt to verify the system works
 */
export function buildTestPrompt(): string {
  return `This is a test message from the ChatGPT Escalation MCP Server.

Please respond with exactly this JSON (and nothing else):

{"ok": true, "message": "Connection successful"}`;
}

/**
 * Extract JSON from a potentially messy response
 * Handles cases where ChatGPT wraps JSON in markdown code blocks
 */
export function extractJson(text: string): string {
  // Try to find JSON in markdown code blocks first
  const codeBlockMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (codeBlockMatch) {
    return codeBlockMatch[1].trim();
  }

  // Try to find a JSON object directly
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    return jsonMatch[0].trim();
  }

  // Return original text if no JSON found
  return text.trim();
}

/**
 * Validate that a response matches the ExpertResponse schema
 */
export function validateExpertResponse(obj: unknown): obj is import("../types.js").ExpertResponse {
  if (typeof obj !== "object" || obj === null) {
    return false;
  }

  const response = obj as Record<string, unknown>;

  // Check required fields
  if (typeof response.guidance !== "string") {
    return false;
  }

  if (!Array.isArray(response.action_plan)) {
    return false;
  }

  if (!response.action_plan.every((item) => typeof item === "string")) {
    return false;
  }

  if (!["low", "medium", "high"].includes(response.priority as string)) {
    return false;
  }

  // Optional field check
  if (
    response.notes_for_user !== undefined &&
    typeof response.notes_for_user !== "string"
  ) {
    return false;
  }

  return true;
}
