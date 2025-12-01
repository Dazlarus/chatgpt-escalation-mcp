# ChatGPT Escalation MCP Server

An MCP (Model Context Protocol) server that enables autonomous coding agents to escalate complex questions to the ChatGPT Desktop app automatically — **ToS-compliant** via native UI automation.

**What this does:** This tool lets autonomous coding agents (Copilot, Claude, Cline, Roo, etc.) escalate hard questions to the *ChatGPT Desktop app* on your computer. It automates ChatGPT the same way a human would — clicking the UI, sending the question, waiting for the response, copying it — then returns the answer to your agent so it can continue working *without you*.

> ### 🖥️ Windows 10/11 Only
> **This tool supports only Windows.** macOS and Linux are not supported and there are no plans to add support.
>
> ### ⚠️ Important Requirements
> - **ChatGPT Desktop app** (Microsoft Store version)
> - Automation controls your ChatGPT window — **don't touch it** during escalations
> - Only **one escalation at a time** (requests are queued)
> - UI changes in ChatGPT may break automation — [open an issue](../../issues) if this happens
>
> ### ✅ ToS Compliant
> This tool only automates your *local* ChatGPT Desktop application. It does **not** automate the web UI, bypass security features, or scrape data.

## Features

- **Two MCP Tools**:
  - `escalate_to_expert` - Send questions to ChatGPT and receive detailed responses
  - `list_projects` - Discover available project IDs from your configuration
- **100% Accurate UI Detection** - Pixel-based detection for sidebar state and response completion
- **OCR-Based Navigation** - PaddleOCR v5 for reliable text extraction and fuzzy matching
- **Async Model Loading** - OCR models preload in background for faster response times
- **Project Organization** - Map multiple projects to different ChatGPT conversations

## How It Works

```
┌─────────────────┐    MCP Protocol    ┌──────────────────┐
│  Coding Agent   │◄──────────────────►│   MCP Server     │
│ (Copilot/Roo)   │                    │  (This Project)  │
└─────────────────┘                    └────────┬─────────┘
                                                │
                                                │ spawn
                                                ▼
                                       ┌──────────────────┐
                                       │  Python Driver   │
                                       │  (Windows)       │
                                       └────────┬─────────┘
                                                │
                                                │ UI Automation
                                                ▼
                                       ┌──────────────────┐
                                       │  ChatGPT Desktop │
                                       │       App        │
                                       └──────────────────┘
```

### Automation Flow

1. **Kill ChatGPT** - Ensures clean state
2. **Open ChatGPT** - Fresh start
3. **Focus Window** - Bring to foreground
4. **Open Sidebar** - Click hamburger menu (pixel detection for state)
5. **Click Project** - OCR + fuzzy matching to find folder
6. **Click Conversation** - OCR + fuzzy matching to find chat
7. **Focus Input** - Click text input area
8. **Send Prompt** - Paste and submit
9. **Wait for Response** - Pixel-based stop button detection
10. **Copy Response** - Robust button probing to find copy button

## System Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Windows** | 10 or 11 | macOS/Linux not supported |
| **ChatGPT Desktop** | Latest | Microsoft Store version |
| **Node.js** | 18+ | For the MCP server |
| **Python** | 3.10+ | For UI automation driver |
| **GPU** | Not required | CPU-only OCR works fine |

### Python Packages
```
pywinauto        # Windows UI automation
pyperclip        # Clipboard access
paddleocr        # Text recognition
paddlepaddle     # PaddleOCR backend
```

### Why Windows Only?

ChatGPT Desktop exposes fully accessible UI elements on Windows via UI Automation APIs. The pixel-based detection and keyboard/mouse automation work reliably on Windows.

macOS has different automation APIs (Accessibility API) that would require a complete rewrite of the driver. Linux doesn't have a ChatGPT Desktop app.

### Tested Environment

| Component | Version | Status |
|-----------|---------|--------|
| **ChatGPT Desktop** | 1.2025.112 | ✅ Tested |
| **Windows 11** | 24H2 (Build 26100.2605) | ✅ Tested |
| **Last Verified** | November 30, 2025 | |

> 💡 **After ChatGPT Updates:** UI automation may break if ChatGPT significantly changes their layout. If you encounter issues after an update, please [open an issue](../../issues) with your ChatGPT version.

## Installation

```powershell
# Clone the repository
git clone https://github.com/yourusername/chatgpt-escalation-mcp.git
cd chatgpt-escalation-mcp

# Install Node.js dependencies
npm install

# Build the project
npm run build

# Install Python dependencies
pip install pywinauto pyperclip paddleocr paddlepaddle
```

## Quick Start

### Step 1: Install ChatGPT Desktop

```powershell
winget install --id=9NT1R1C2HH7J --source=msstore --accept-package-agreements --accept-source-agreements
```

Or install from the Microsoft Store: search "ChatGPT" by OpenAI.

### Step 2: Create a Conversation in ChatGPT

1. Open ChatGPT Desktop and sign in
2. Create a new **Project** (folder) called `Agent Expert Help`
3. Inside that project, create a new conversation called `Copilot Escalations`
4. Send this initial message to set the context:

```
You are an expert software architect. I'll send you technical questions from my coding agent (GitHub Copilot, Claude, etc.) when it gets stuck. 

For each question:
1. Analyze the problem thoroughly
2. Provide specific, actionable guidance
3. Include code examples when helpful
4. Explain WHY a solution works, not just what to do

The questions will include context about what the agent already tried.
```

### Step 3: Configure the MCP Server

Create the config file at `~/.chatgpt-escalation/config.json`:

```powershell
# Create config directory
New-Item -ItemType Directory -Path "$env:USERPROFILE\.chatgpt-escalation" -Force

# Create config file (edit the path in notepad)
notepad "$env:USERPROFILE\.chatgpt-escalation\config.json"
```

Paste this configuration:

```json
{
  "chatgpt": {
    "platform": "win",
    "responseTimeout": 120000,
    "projects": {
      "default": {
        "folder": "Agent Expert Help",
        "conversation": "Copilot Escalations"
      }
    }
  },
  "logging": {
    "level": "info"
  }
}
```

### Step 4: Add to Your MCP Client

**For VS Code with GitHub Copilot** (settings.json or mcp config):
```json
{
  "mcpServers": {
    "chatgpt-escalation": {
      "command": "node",
      "args": ["C:/path/to/chatgpt-escalation-mcp/dist/src/server.js"]
    }
  }
}
```

**For Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "chatgpt-escalation": {
      "command": "node",
      "args": ["C:/path/to/chatgpt-escalation-mcp/dist/src/server.js"]
    }
  }
}
```

> ⚠️ Use forward slashes `/` in paths, or escape backslashes as `\\`

### Step 5: Teach Your Agent When to Escalate

Add escalation instructions to your agent. Choose the format that matches your tool:

<details>
<summary><strong>GitHub Copilot</strong> (.github/copilot-instructions.md)</summary>

```markdown
## Expert Escalation Protocol

You have access to the `escalate_to_expert` MCP tool that sends questions to ChatGPT for expert guidance.

### When to Escalate
- You've tried 3+ approaches without success
- The problem requires specialized domain knowledge
- You're unsure if the fundamental approach is correct
- You're hitting consistent failure patterns you can't diagnose

### How to Escalate
Use the `escalate_to_expert` tool with:
- `project`: "default" (or specific project ID)
- `reason`: Why you're stuck (be specific)
- `question`: The technical question
- `attempted`: What you already tried and results
- `artifacts`: Relevant code snippets

### After Escalation
Read the full response before implementing. ChatGPT often provides multiple approaches - pick the most appropriate one for the context.
```

</details>

<details>
<summary><strong>Cline / Roo Code</strong> (.clinerules or .roo/rules)</summary>

```markdown
## Expert Escalation Protocol

You have access to the `escalate_to_expert` MCP tool. Use it when stuck.

### Escalation Triggers
1. **Accuracy plateau** - 3+ attempts with no improvement
2. **Consistent failures** - Same error pattern despite different approaches
3. **Domain gap** - Problem needs specialized knowledge you lack
4. **Architecture uncertainty** - Unsure if approach is fundamentally correct

### Before Escalating
Stop and ask the user: "I've tried [X approaches] but I'm hitting [limitation]. Should I escalate to ChatGPT?"

If yes, call `escalate_to_expert` with:
- `project`: "default"
- `reason`: Brief description of why you're stuck
- `question`: Specific technical question
- `attempted`: Numbered list of what you tried and results
- `artifacts`: Relevant code snippets

### Question Format
Structure your question clearly:
- **Problem:** One sentence description
- **Context:** Technical details, frameworks, constraints
- **What I tried:** Numbered list with results
- **Specific questions:** What you need answered

### After Response
1. Read the FULL response before implementing
2. Identify the recommended approach (there may be multiple)
3. Implement incrementally - test each suggestion
4. If unclear, ask user for clarification before proceeding
```

</details>

<details>
<summary><strong>OpenAI Codex CLI</strong> (AGENTS.md or instructions)</summary>

```markdown
## Expert Escalation via ChatGPT

The `escalate_to_expert` MCP tool lets you ask ChatGPT for help on complex problems.

### When to Use
- Multiple failed attempts on a problem
- Need domain expertise (ML, systems, security, etc.)
- Debugging issues that don't make sense
- Architecture or design decisions

### Tool Usage
```
escalate_to_expert({
  project: "default",
  reason: "Brief explanation of the blocker",
  question: "Specific technical question",
  attempted: "What was tried and what happened",
  artifacts: [{type: "file_snippet", pathOrLabel: "file.py", content: "..."}]
})
```

### Best Practices
- Be specific about what you tried and exact error messages
- Include relevant code snippets in artifacts
- Ask focused questions, not "help me fix this"
- After receiving response, implement suggestions step by step
```

</details>

<details>
<summary><strong>Claude Desktop / Other MCP Clients</strong></summary>

```markdown
## Expert Escalation Protocol

You have access to the `escalate_to_expert` MCP tool that sends questions to ChatGPT.

### When to Escalate
- Tried 3+ approaches without success
- Problem requires specialized domain knowledge
- Unsure if fundamental approach is correct
- Hitting consistent failure patterns

### Tool Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| project | Yes | Project ID (usually "default") |
| reason | Yes | Why you're escalating |
| question | Yes | The technical question |
| attempted | No | What you tried and results |
| artifacts | No | Code snippets [{type, pathOrLabel, content}] |

### After Response
Read fully before implementing. Pick the most appropriate suggestion for the context.
```

</details>

#### Example Escalation Call

```json
{
  "project": "default",
  "reason": "Authentication flow failing silently, can't identify root cause",
  "question": "Why would JWT refresh tokens work in development but fail in production with no error messages?",
  "attempted": "1. Checked token expiry (valid), 2. Verified CORS (correct), 3. Tested with Postman (works)",
  "artifacts": [{"type": "file_snippet", "pathOrLabel": "auth.ts", "content": "..."}]
}
```

## Configuration Reference

Config file location: `%USERPROFILE%\.chatgpt-escalation\config.json`

```json
{
  "chatgpt": {
    "platform": "win",
    "responseTimeout": 120000,
    "projects": {
      "my-project": {
        "folder": "My Project Folder",
        "conversation": "Expert Help Chat"
      },
      "simple-project": "Just a Conversation Title"
    }
  },
  "logging": {
    "level": "info"
  }
}
```

### Project Configuration

Projects can be configured two ways:

**Simple** (conversation at root level in ChatGPT sidebar):
```json
"project-id": "Conversation Title"
```

**With Folder** (conversation inside a ChatGPT project folder):
```json
"project-id": {
  "folder": "Project Folder Name",
  "conversation": "Conversation Title"
}
```

### Multiple Projects

You can map different coding projects to different ChatGPT conversations:

```json
"projects": {
  "webapp": {
    "folder": "Web Projects",
    "conversation": "React App Help"
  },
  "api": {
    "folder": "Backend Projects", 
    "conversation": "API Design Help"
  },
  "default": "General Coding Help"
}
```

Then agents can escalate to the right context:
```json
{"project": "webapp", "question": "How to optimize React re-renders?"}
{"project": "api", "question": "Best practices for REST pagination?"}
```

## MCP Tools Reference

#### `escalate_to_expert`

Send a question to ChatGPT via the desktop app.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | Yes | Project ID from config (use `list_projects` to discover) |
| `reason` | string | Yes | Why you're escalating (helps ChatGPT understand context) |
| `question` | string | Yes | The specific technical question |
| `attempted` | string | No | What you've already tried and the results |
| `projectContext` | string | No | Additional context about the codebase |
| `artifacts` | array | No | Code snippets, logs, or notes (see below) |

**Artifact format:**
```json
{
  "type": "file_snippet" | "log" | "note",
  "pathOrLabel": "src/auth.ts",
  "content": "// the actual code or content"
}
```

#### `list_projects`

Discover available project IDs from your configuration. Call this first if you don't know what projects are available.

**Returns:**
```json
{
  "projects": ["default", "webapp", "api"],
  "count": 3
}
```

## Important Notes

### ChatGPT Conversation Setup

For best results, start each project's ChatGPT conversation with a system prompt that establishes the expert role:

> "You are an expert software architect helping with [PROJECT_NAME]. When I send questions, provide detailed technical answers with code examples when appropriate."

### During Use

- **Keep ChatGPT Desktop installed** (it will be opened/closed automatically)
- **Don't interact with ChatGPT** while escalation is in progress
- Automation takes ~30-120 seconds depending on response length
- Works best when you're AFK or focused on other tasks

### Version Compatibility

| ChatGPT Desktop Version | Status | Notes |
|-------------------------|--------|-------|
| 1.2025.112 | ✅ Supported | Last tested Nov 30, 2025 |
| Older versions | ⚠️ Unknown | May work, not tested |
| Future versions | ⚠️ Unknown | May break if UI changes significantly |

If a ChatGPT update breaks automation, [open an issue](../../issues) with your version number.

## What Happens During Escalation

When your agent calls `escalate_to_expert`, here's the full sequence:

```
1. 🔄 Kill ChatGPT          → Ensures clean state (no stale modals)
2. 🚀 Launch ChatGPT        → Fresh start via shell
3. 🎯 Focus Window          → Bring to foreground
4. 📂 Open Sidebar          → Click hamburger menu (if not already open)
5. 📁 Click Project Folder  → OCR finds folder name, clicks it
6. 💬 Click Conversation    → OCR finds conversation name, clicks it
7. ✏️  Focus Input           → Click the text input area
8. 📋 Send Question         → Paste question + press Enter
9. ⏳ Wait for Response     → Poll until stop button disappears
10. 📄 Copy Response        → Navigate to copy button, click it
11. ✅ Return to Agent      → JSON response sent via MCP
```

Total time: **30-120 seconds** depending on response length.

### Automation Behavior Summary

| Behavior | Description |
|----------|-------------|
| **On escalation** | ChatGPT Desktop is closed and relaunched fresh |
| **Window positioning** | Brought to foreground, not moved |
| **Conversation selection** | Fuzzy match on title in sidebar (OCR-based) |
| **Sending message** | Pasted into composer → Enter |
| **Completion detection** | Pixel analysis of stop button region |
| **Copying response** | Keyboard navigation to copy button |
| **Returned format** | JSON with response text |

> 💡 **Why restart ChatGPT each time?** This ensures a deterministic window state. ChatGPT Desktop can get into weird states (modals open, input focused wrong, scroll position off) that break automation. A fresh start is more reliable than handling every edge case.

## How Detection Works

This section explains the pixel-based detection for developers who want to understand or modify the automation.

### Sidebar State Detection
```
┌─────────────────────────────────┐
│ [X]  ← X button appears here   │
│      when sidebar is open      │
│                                │
│  Sidebar content...            │
└─────────────────────────────────┘
```
- Samples a 20x20 pixel region where the X button should be
- Counts pixels darker than brightness threshold (100)
- **>50 dark pixels** = sidebar is open
- **<50 dark pixels** = sidebar is closed

### Response Generation Detection
```
┌─────────────────────────────────┐
│                                │
│  Response text...              │
│                                │
│           [■ Stop]  ← Stop     │
│                       button   │
└─────────────────────────────────┘
```
- Samples the stop button region
- Counts non-white pixels in the area
- **60 < pixels < 400** = currently generating (stop button visible)
- **Outside range** = generation complete
- Polls every 500ms until complete

### Copy Button Detection
- After response completes, uses Shift+Tab to navigate backwards
- Skips first 4 positions (thumbs up/down, regenerate, etc.)
- At each position: presses Enter, checks if clipboard changed
- Stops when new content appears in clipboard

## Development

```powershell
# Watch mode
npm run dev

# Build
npm run build
```

## Troubleshooting

### "ChatGPT window not found"
- Make sure ChatGPT Desktop app is installed
- The automation will start it automatically

### "Conversation not found"
- Verify the conversation title in config matches exactly
- Check that the project folder name is correct
- The conversation must exist before first use

### "Response timeout"
- Increase `responseTimeout` in config for longer responses
- Check if ChatGPT is rate-limited or experiencing issues

### OCR not working
```powershell
# Reinstall PaddleOCR
pip install --upgrade paddleocr paddlepaddle
```

### Windows automation issues
```powershell
# Reinstall automation dependencies
pip install --upgrade pywinauto pyperclip pywin32
```

### Logs

Logs are written to stderr and can be captured by your MCP client. Set `logging.level` to `"debug"` in config for verbose output.

## Verification Checklist

Before your first escalation, confirm:

- [ ] Windows 10 or 11
- [ ] ChatGPT Desktop installed (Microsoft Store version)
- [ ] ChatGPT Desktop opens and you're logged in
- [ ] Created the project folder in ChatGPT (e.g., "Agent Expert Help")
- [ ] Created the conversation inside that folder (e.g., "Copilot Escalations")
- [ ] Conversation title in config matches **exactly** (case-sensitive)
- [ ] Config file exists at `%USERPROFILE%\.chatgpt-escalation\config.json`
- [ ] MCP client configured with correct path to `dist/src/server.js`
- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.10+ installed (`python --version`)
- [ ] Python packages installed (`pip list | findstr pywinauto`)

## FAQ

<details>
<summary><strong>Can I keep working while it runs?</strong></summary>

Yes, but **don't interact with the ChatGPT window**. The automation controls mouse/keyboard input to that specific window. You can use other apps normally.
</details>

<details>
<summary><strong>Can I use this for multiple agents simultaneously?</strong></summary>

No. Only one escalation at a time. If you have multiple agents, they'll queue up and be processed sequentially.
</details>

<details>
<summary><strong>Can this escalate to multiple ChatGPT conversations?</strong></summary>

Yes! Configure multiple projects in your config, each pointing to different folders/conversations. Your agent specifies which project to use.
</details>

<details>
<summary><strong>Will this work on macOS in the future?</strong></summary>

Unlikely. macOS has different automation APIs (Accessibility API) that would require a complete driver rewrite. The Windows-only scope is intentional to keep the project maintainable.
</details>

<details>
<summary><strong>Can I use Ollama or a local LLM instead?</strong></summary>

Not with this tool — it specifically automates the ChatGPT Desktop app. For local LLMs, use a different MCP server that calls Ollama's API directly.
</details>

<details>
<summary><strong>How long does an escalation take?</strong></summary>

Typically 30-120 seconds:
- ~10s to open ChatGPT and navigate
- ~5-90s for ChatGPT to generate response (depends on length)
- ~5s to copy and return
</details>

<details>
<summary><strong>The first run is really slow. Why?</strong></summary>

PaddleOCR downloads its model files (~100MB) on first use. Subsequent runs are much faster, and the model preloads in the background.
</details>

## Uninstall

```powershell
# Remove config directory
Remove-Item -Recurse -Force "$env:USERPROFILE\.chatgpt-escalation"

# Remove from your MCP client config
# (edit your settings.json or claude_desktop_config.json)

# Optionally uninstall Python dependencies
pip uninstall pywinauto pyperclip paddleocr paddlepaddle
```

## Security

This tool **never** automates anything outside the ChatGPT Desktop window. It never reads unrelated windows, captures screens of other apps, or interacts with other applications. All automation is scoped to the ChatGPT process.

## License

MIT

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

