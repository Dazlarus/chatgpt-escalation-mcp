import * as fs from "fs";
import * as path from "path";

export type LogLevel = "debug" | "info" | "warn" | "error";

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const COLORS = {
  reset: "\x1b[0m",
  dim: "\x1b[2m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
  white: "\x1b[37m",
};

export class Logger {
  private level: LogLevel;
  private logFile?: string;
  private fileStream?: fs.WriteStream;
  private context: string;

  constructor(context: string, level: LogLevel = "info", logFile?: string) {
    this.context = context;
    this.level = level;
    this.logFile = logFile;

    if (logFile) {
      const dir = path.dirname(logFile);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      this.fileStream = fs.createWriteStream(logFile, { flags: "a" });
    }
  }

  private shouldLog(level: LogLevel): boolean {
    return LOG_LEVELS[level] >= LOG_LEVELS[this.level];
  }

  private formatTimestamp(): string {
    return new Date().toISOString();
  }

  private formatMessage(level: LogLevel, message: string, data?: unknown): string {
    const timestamp = this.formatTimestamp();
    const dataStr = data ? ` ${JSON.stringify(data)}` : "";
    return `[${timestamp}] [${level.toUpperCase()}] [${this.context}] ${message}${dataStr}`;
  }

  private colorize(level: LogLevel, message: string): string {
    const colors: Record<LogLevel, string> = {
      debug: COLORS.dim,
      info: COLORS.blue,
      warn: COLORS.yellow,
      error: COLORS.red,
    };
    return `${colors[level]}${message}${COLORS.reset}`;
  }

  private log(level: LogLevel, message: string, data?: unknown): void {
    if (!this.shouldLog(level)) return;

    const formatted = this.formatMessage(level, message, data);

    // Write to stderr (MCP servers use stdout for protocol)
    console.error(this.colorize(level, formatted));

    // Write to file if configured
    if (this.fileStream) {
      this.fileStream.write(formatted + "\n");
    }
  }

  debug(message: string, data?: unknown): void {
    this.log("debug", message, data);
  }

  info(message: string, data?: unknown): void {
    this.log("info", message, data);
  }

  warn(message: string, data?: unknown): void {
    this.log("warn", message, data);
  }

  error(message: string, data?: unknown): void {
    this.log("error", message, data);
  }

  child(context: string): Logger {
    return new Logger(`${this.context}:${context}`, this.level, this.logFile);
  }

  setLevel(level: LogLevel): void {
    this.level = level;
  }

  close(): void {
    if (this.fileStream) {
      this.fileStream.end();
    }
  }
}

// Default logger instance
let defaultLogger: Logger | null = null;

export function initializeLogger(level: LogLevel = "info", logFile?: string): Logger {
  defaultLogger = new Logger("escalation-mcp", level, logFile);
  return defaultLogger;
}

export function getLogger(context?: string): Logger {
  if (!defaultLogger) {
    defaultLogger = new Logger("escalation-mcp", "info");
  }
  return context ? defaultLogger.child(context) : defaultLogger;
}
