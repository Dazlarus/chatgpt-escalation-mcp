# Safety Guardrails

The ChatGPT Desktop automation includes robust safety guardrails to handle common interruptions and failures during operation.

## Overview

Real-world automation faces many challenges:
- **Focus loss**: User alt-tabs to another window
- **Window minimization**: User clicks minimize or Win+D
- **Mouse movement**: User moves mouse during automation
- **Window handle invalidation**: ChatGPT restart or crash mid-flow
- **Occlusion**: Another window opens on top of ChatGPT

The safety guardrail system detects and recovers from these scenarios automatically.

## Core Safety Components

### 1. Foreground Verification (`_ensure_foreground`)

**What it does:**
- Checks if ChatGPT window is the foreground window before every UI action
- Automatically restores focus if lost
- Uses multiple methods: `SetForegroundWindow`, `BringWindowToTop`
- Retries up to 3 times with increasing delays

**When it runs:**
- Before every click operation via `_safe_click`
- Before keyboard input (Ctrl+V, Shift+Tab, Enter)
- Before mouse scroll operations
- Before window state detection (sidebar open, response generation)

**Example logging:**
```
[safety] Window lost focus (attempt 1/3), restoring...
[safety] ✓ Focus restored (attempt 1)
[safe_click] ✓ Clicked at (245, 180) - sidebar item 'My Project'
```

### 2. Window State Checks (`_is_window_ready`)

**What it does:**
- Validates window handle is still valid (`IsWindow`)
- Detects if window is minimized (`IsIconic`)
- Checks if window is visible (`IsWindowVisible`)
- Returns `False` if window is in an invalid state

**When it runs:**
- At the start of critical steps (step4, step5, step6)
- Before operations in `_retry_with_recovery`
- After focus restoration attempts

**Example logging:**
```
[safety] ✗ Window is minimized
[safety] ✗ Window handle is invalid
```

### 3. Window Handle Refresh (`_refresh_hwnd`)

**What it does:**
- Re-discovers ChatGPT window via process enumeration
- Updates `self.hwnd` and `self.window_rect`
- Used when window handle becomes invalid (ChatGPT restart, UAC prompt, etc.)

**When it runs:**
- When `_is_window_ready` returns `False`
- During retry recovery logic
- After operations that might invalidate the handle

**Example logging:**
```
[safety] Refreshing window handle...
[safety] ✓ Window handle refreshed (hwnd=12345678)
```

### 4. Retry with Recovery (`_retry_with_recovery`)

**What it does:**
- Wraps operations in retry loop (max 3 attempts)
- Pre-checks window readiness before each attempt
- Attempts handle refresh if window invalid
- Restores minimized windows (`SW_RESTORE`)
- Ensures foreground before operation
- Uses exponential backoff (0.5s, 1s, 2s)

**How to use:**
```python
def my_operation():
    # Do something that might fail
    return self._find_and_click_sidebar_item("Project")

# Wrap in retry
success = self._retry_with_recovery(
    my_operation,
    "click sidebar project",
    max_attempts=3
)
```

**Example logging:**
```
[retry] click sidebar project: Window not ready (attempt 1/3)
[safety] Refreshing window handle...
[retry] click sidebar project: ✓ Succeeded on attempt 2
```

### 5. Safe Click (`_safe_click`)

**What it does:**
- Ensures window is foreground before clicking
- Performs the click
- Logs success/failure with coordinates and description

**Used everywhere:**
- Sidebar item clicks (project, conversation selection)
- Hamburger menu clicks (open sidebar)
- Input field anchor clicks (for tab navigation)
- Project view conversation clicks
- Corrective clicks (for off-by-one OCR corrections)

**Example logging:**
```
[safe_click] ✓ Clicked at (245, 180) - sidebar item 'My Project'
[safe_click] ✗ Could not ensure foreground for hamburger menu
```

## Recovery Strategies

### Focus Loss (Alt+Tab)

**Scenario**: User switches to another window during automation

**Detection**: `GetForegroundWindow() != self.hwnd`

**Recovery**:
1. `SetForegroundWindow(self.hwnd)` — primary method
2. `BringWindowToTop(self.hwnd)` — fallback if primary fails
3. Retry up to 3 times with 0.2s delays
4. If all fail, operation returns `False` and error propagates up

**Example timeline**:
```
[FLOW] STEP 4: Opening sidebar...
[safety] Window lost focus (attempt 1/3), restoring...
[safety] ✓ Focus restored (attempt 1)
[safe_click] ✓ Clicked at (245, 80) - hamburger menu
[FLOW] ✓ VERIFIED: Sidebar is open
```

### Window Minimized (Win+D)

**Scenario**: User minimizes ChatGPT or minimizes all windows

**Detection**: `IsIconic(self.hwnd) == True`

**Recovery**:
1. Detected by `_is_window_ready()` at start of step
2. Calls `ShowWindow(self.hwnd, SW_RESTORE)` to restore
3. Waits 0.5s for animation to complete
4. Re-checks readiness
5. If still minimized, step fails and error propagates

**Example timeline**:
```
[FLOW] STEP 5: Clicking project 'My Project'...
[safety] ✗ Window is minimized
[FLOW] ✗ Window not ready - attempting recovery
[safety] Refreshing window handle...
[safety] ✓ Window handle refreshed (hwnd=12345678)
[FLOW] (restored window, continuing)
```

### Handle Invalidation (ChatGPT Restart)

**Scenario**: ChatGPT crashes, UAC prompt causes handle invalidation, or user force-closes and restarts

**Detection**: `IsWindow(self.hwnd) == False`

**Recovery**:
1. `_is_window_ready()` detects invalid handle
2. Calls `_refresh_hwnd()` to re-discover ChatGPT
3. Enumerates all windows looking for `chatgpt.exe` process
4. Updates `self.hwnd` and `self.window_rect`
5. If not found, operation fails

**Example timeline**:
```
[FLOW] STEP 6: Clicking conversation 'Test Chat'...
[safety] ✗ Window handle is invalid
[FLOW] ✗ Window not ready - attempting recovery
[safety] Refreshing window handle...
[safety] ✓ Window handle refreshed (hwnd=87654321)
[FLOW] (continuing with new handle)
```

### Mouse Movement (User Intervention)

**Scenario**: User moves mouse during automation, potentially clicking elsewhere

**Impact**: Limited — automation uses absolute screen coordinates and restores focus before each action

**Mitigation**:
- **Foreground verification** ensures clicks go to ChatGPT even if user clicked elsewhere
- **Window rect refresh** updates coordinates if window moved
- **Retry logic** recovers from misclicks caused by timing issues
- **Hover detection** validates sidebar selections after click, applies corrective clicks if needed

**Note**: Mouse movement itself doesn't break automation. Only if user clicks another window (causing focus loss) does recovery activate.

## Operation Flow with Safety

Here's what happens during a typical sidebar click:

1. **Pre-check**: `_is_window_ready()` validates window state
2. **Recovery** (if needed): Refresh handle, restore minimize, re-check
3. **OCR scan**: Capture sidebar, find target text via OCR
4. **Safe click**: `_safe_click()` ensures foreground, then clicks
5. **Hover validation**: Detect highlighted item, measure delta from click
6. **Corrective click** (if needed): If delta > 18px, click ±28px to correct
7. **Verification**: Re-check hover, OCR nearest text, fuzzy match target

Each step includes safety checks and recovery logic.

## Configuration

Most safety parameters are hard-coded for reliability, but can be tuned if needed:

### Retry Limits
```python
max_attempts = 3  # _ensure_foreground, _retry_with_recovery
```

### Backoff Delays
```python
time.sleep(0.5 * attempt)  # Exponential backoff in retry loop
```

### Foreground Restore Delays
```python
time.sleep(0.2)  # After SetForegroundWindow
time.sleep(0.3)  # Between retry attempts
```

### Window Restore Delays
```python
time.sleep(0.5)  # After SW_RESTORE (minimize → normal)
```

## Limitations

### What Safety Guardrails Can Handle
- ✅ User alt-tabs to another window (focus loss)
- ✅ User minimizes ChatGPT (Win+D, minimize button)
- ✅ Another window opens on top of ChatGPT (occlusion)
- ✅ ChatGPT restarts mid-flow (handle invalidation)
- ✅ User moves mouse (no impact, focus restored before actions)
- ✅ Transient focus loss from system prompts (UAC, notifications)

### What Safety Guardrails Cannot Handle
- ❌ User closes ChatGPT entirely (no window to recover)
- ❌ User logs out or locks screen (session invalidation)
- ❌ System suspend/hibernate (all processes paused)
- ❌ ChatGPT frozen/unresponsive (no API to detect)
- ❌ User clicks inside ChatGPT during automation (may disrupt state, but focus remains)
- ❌ Screen resolution change mid-flow (coordinates become invalid)

### Expected Failure Modes
If recovery fails after 3 attempts, the operation returns `False` and the error propagates:
```json
{
  "success": false,
  "error": "Failed to open sidebar",
  "failed_step": 4
}
```

This allows the MCP server to report the failure to the calling agent with context about which step failed.

## Diagnostic Logging

All safety operations log to `stderr` with `[safety]` prefix:

```
[safety] Window lost focus (attempt 1/3), restoring...
[safety] ✓ Focus restored (attempt 1)
[safety] ✗ Window is minimized
[safety] Refreshing window handle...
[safety] ✓ Window handle refreshed (hwnd=12345678)
```

Additional operation-specific prefixes:
- `[safe_click]` — Click operations with foreground verification
- `[retry]` — Retry loop with recovery
- `[FLOW]` — High-level step logging
- `[copy]` — Copy button navigation and validation
- `[scroll]` — Sidebar scroll operations
- `[focus]` — Input focus detection and restoration

To see full diagnostic output when testing via MCP, set log level to `debug` in your MCP client.

## Testing Safety Guardrails

### Manual Testing Scenarios

1. **Focus Loss Test**:
   - Start escalation via MCP
   - Alt+tab to another window mid-flow
   - Expected: Automation restores focus and continues

2. **Minimize Test**:
   - Start escalation
   - Press Win+D to minimize all windows
   - Expected: Automation restores ChatGPT and continues

3. **Occlusion Test**:
   - Start escalation
   - Open another window on top of ChatGPT
   - Expected: Automation brings ChatGPT to front and continues

4. **Mouse Movement Test**:
   - Start escalation
   - Move mouse around screen
   - Expected: Automation continues unaffected

5. **ChatGPT Restart Test**:
   - Start escalation, let it reach step 5
   - Close and restart ChatGPT manually
   - Expected: Handle refresh recovers (if timing allows)

### Automated Testing

The `robust_flow.py` test harness can simulate some scenarios:

```python
# Test with simulated interruptions
flow = RobustChatGPTFlow()
flow.execute_full_flow(
    project_name="Test Project",
    conversation_name="Test Chat",
    prompt="Test question"
)
# Manually trigger alt+tab during execution
```

## Future Enhancements

Potential improvements to safety guardrails:

1. **Frozen process detection**: Detect if ChatGPT is unresponsive (hung UI thread)
2. **Screen resolution validation**: Detect resolution changes and recompute coordinates
3. **Graceful degradation**: Continue with reduced functionality if some operations fail
4. **Session state recovery**: Save progress and resume from last successful step
5. **Parallel validation**: Check multiple signals (title, hover, OCR) for stronger verification
6. **Adaptive retry timing**: Adjust backoff based on failure type (minimize needs longer than focus loss)

For now, the current guardrails handle the most common real-world interruptions effectively.
