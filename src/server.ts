import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import type { EscalationPacket, ExpertBackend, ExpertResponse, ProjectEntry } from "./types.js";
import { loadConfig, validateConfig, getConfigSummary, getProjectFolder, getProjectConversation } from "./util/configLoader.js";
import { initializeLogger, getLogger } from "./util/logging.js";
import { createChatGPTDesktopBackend } from "./backends/chatgpt-desktop.js";

// Tool input schema for MCP
const ESCALATE_TOOL_SCHEMA = {
  type: "object",
  properties: {
    backend: {
      type: "string",
      enum: ["chatgpt-desktop", "chatgpt-desktop-vision"],
      default: "chatgpt-desktop",
      description: "Backend to use for escalation",
    },
    project: {
      type: "string",
      description: "Project ID defined in user config",
    },
    reason: {
      type: "string",
      description: "Why are you escalating this question?",
    },
    question: {
      type: "string",
      description: "The specific question you need answered",
    },
    attempted: {
      type: "string",
      description: "What have you already tried?",
    },
    projectContext: {
      type: "string",
      description: "Relevant context about the project",
    },
    artifacts: {
      type: "array",
      description: "Supporting code snippets, logs, or notes",
      items: {
        type: "object",
        properties: {
          type: {
            type: "string",
            enum: ["file_snippet", "log", "note"],
            description: "Type of artifact",
          },
          pathOrLabel: {
            type: "string",
            description: "File path or label for the artifact",
          },
          content: {
            type: "string",
            description: "Content of the artifact",
          },
        },
        required: ["type", "content"],
      },
    },
  },
  required: ["project", "reason", "question"],
} as const;

// Tool input schema for list_projects (no parameters needed)
const LIST_PROJECTS_TOOL_SCHEMA = {
  type: "object",
  properties: {},
  required: [],
} as const;

/**
 * Create and configure the MCP server
 */
export async function createServer(): Promise<Server> {
  // Initialize configuration
  const config = loadConfig();
  const validation = validateConfig(config);

  // Initialize logging
  initializeLogger(config.logging.level, config.logging.file);
  const logger = getLogger("server");

  logger.info("Starting ChatGPT Desktop Escalation MCP Server");
  logger.debug("Configuration loaded", { summary: getConfigSummary(config) });

  if (!validation.valid) {
    logger.error("Configuration validation failed", { errors: validation.errors });
    throw new Error(`Invalid configuration: ${validation.errors.join(", ")}`);
  }

  if (validation.warnings.length > 0) {
    validation.warnings.forEach((warning) => logger.warn(warning));
  }

  // Initialize backend
  let backend: ExpertBackend | null = null;

  function getBackend(): ExpertBackend {
    if (!backend) {
      backend = createChatGPTDesktopBackend(config);
    }
    return backend;
  }

  // Create MCP server
  const server = new Server(
    {
      name: "chatgpt-escalation-mcp",
      version: "1.0.0",
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // List available tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "list_projects",
          description:
            "List all available project IDs that can be used with escalate_to_expert. " +
            "Call this first to discover what projects are configured before escalating.",
          inputSchema: LIST_PROJECTS_TOOL_SCHEMA,
        },
        {
          name: "escalate_to_expert",
          description:
            "Escalate a question to an expert (ChatGPT Desktop) when you are stuck or need guidance. " +
            "Use this when you've tried reasonable approaches but are blocked. " +
            "Returns structured guidance with an action plan. " +
            "Call list_projects first to see available project IDs.",
          inputSchema: ESCALATE_TOOL_SCHEMA,
        },
      ],
    };
  });

  // Handle tool calls
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    // Handle list_projects tool
    if (name === "list_projects") {
      logger.info("Listing available projects");
      
      const projects = config.chatgpt.projects;
      const projectList = Object.entries(projects).map(([id, entry]) => {
        const folder = getProjectFolder(config, id);
        const conversation = getProjectConversation(config, id);
        return {
          id,
          folder: folder || "(root level)",
          conversation: conversation || "(not configured)",
        };
      });

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              available_projects: projectList,
              usage: "Use one of the 'id' values as the 'project' parameter when calling escalate_to_expert",
            }, null, 2),
          },
        ],
      };
    }

    // Handle escalate_to_expert tool
    if (name !== "escalate_to_expert") {
      throw new Error(`Unknown tool: ${name}`);
    }

    logger.info("Received escalation request", {
      project: (args as Record<string, unknown>)?.project,
    });

    try {
      // Validate input
      const rawArgs = args as Record<string, unknown> | undefined;

      if (!rawArgs) {
        throw new Error("No arguments provided");
      }

      const packet: EscalationPacket = {
        backend:
          (rawArgs.backend as EscalationPacket["backend"]) || "chatgpt-desktop",
        project: rawArgs.project as string,
        reason: rawArgs.reason as string,
        question: rawArgs.question as string,
        attempted: rawArgs.attempted as string | undefined,
        projectContext: rawArgs.projectContext as string | undefined,
        artifacts: rawArgs.artifacts as EscalationPacket["artifacts"],
      };

      if (!packet.project) {
        throw new Error("Missing required field: project");
      }
      if (!packet.reason) {
        throw new Error("Missing required field: reason");
      }
      if (!packet.question) {
        throw new Error("Missing required field: question");
      }

      // Get backend
      const b = getBackend();

      // Send escalation
      const response: ExpertResponse = await b.sendEscalation(packet);

      logger.info("Escalation completed", {
        project: packet.project,
        priority: response.priority,
      });

      // Return structured response
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(response, null, 2),
          },
        ],
      };
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      const errorStack = error instanceof Error ? error.stack : undefined;
      
      logger.error("Escalation failed", { 
        message: errorMessage,
        stack: errorStack,
      });

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                error: true,
                message: errorMessage,
                guidance:
                  "The escalation request failed. Please check the error message and try again.",
                action_plan: [
                  "Review the error message",
                  "Verify ChatGPT Desktop is open and running",
                  "Verify your configuration with 'chatgpt-escalation-mcp doctor'",
                  "Ensure you have run 'chatgpt-escalation-mcp init' to set up conversations",
                ],
                priority: "high",
              },
              null,
              2
            ),
          },
        ],
        isError: true,
      };
    }
  });

  // Handle graceful shutdown
  process.on("SIGINT", async () => {
    logger.info("Shutting down...");
    if (backend) {
      await backend.cleanup();
    }
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    logger.info("Shutting down...");
    if (backend) {
      await backend.cleanup();
    }
    process.exit(0);
  });

  return server;
}

/**
 * Run the MCP server with stdio transport
 */
export async function runServer(): Promise<void> {
  const server = await createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
