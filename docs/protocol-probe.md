# Protocol Probe (MCP)

This probe validates that the MCP server is discoverable and responds correctly to core protocol flows without relying on the CLI.

What it does
- Starts the server over stdio and performs:
  - initialize/connect
  - list tools and validate input schema for `escalate_to_expert`
  - call `list_projects` and parse JSON
  - call `escalate_to_expert` and assert a non-error, structured JSON response
- Prints server logs from stderr for easy diagnosis
- Exits with code 0 on success; non‑zero on failure

Prerequisites
- Windows with ChatGPT Desktop installed and signed in
- A valid config with at least one project (see `chatgpt-escalation-mcp init`)
- Python 3 with `pywinauto` and `pyperclip` installed
  - Install with: `npm run setup-python`

Usage
```powershell
# From repo root
npm run probe
# or
node tools/mcp_protocol_probe.js
```

Expected output (abridged)
```
[INFO] [escalation-mcp:server] Starting ...
[probe] Connected
[probe] Tools: [ 'list_projects', 'escalate_to_expert' ]
[probe] Projects OK
[probe] Calling escalate_to_expert...
[INFO] [escalation-mcp:chatgpt-desktop] Escalation completed successfully
[probe] Escalation response OK
[probe] SUCCESS
```

Troubleshooting
- Probe fails at tools discovery:
  - Ensure Node 18+ and run `npm run build` if using from source.
- `list_projects` returns non‑JSON:
  - Check your config file and run `chatgpt-escalation-mcp doctor`.
- Escalation `isError=true` or `{ error: true }` JSON:
  - Confirm ChatGPT Desktop is open and responsive.
  - Verify projects are configured: `chatgpt-escalation-mcp init`.
  - Increase timeout in your config if responses are slow.
  - Ensure Python deps are present: `npm run setup-python`.

Notes
- The probe uses long timeouts (10m) for tool calls to accommodate slow UI operations.
- Server logs print to stderr; redirect/stdout remains reserved for MCP protocol.
