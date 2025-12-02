# Chaos Testing Invariants

This document defines the invariants that MUST hold even under adversarial chaos conditions.
These are the "never break" rules for the ChatGPT automation system.

## Critical Invariants

### 1. Prompt Integrity
**INVARIANT**: The prompt sent to ChatGPT must EXACTLY match the intended prompt.

- **Verification**: `_verify_prompt_entry()` copies the input field content and compares to expected
- **Failure Mode**: Chaos typing garbage into input before paste completes
- **Mitigation**: Ctrl+A, Ctrl+C to copy, compare, retry if mismatch
- **Never**: Send Enter if prompt verification fails

### 2. Response Provenance
**INVARIANT**: The copied response must be the response to OUR prompt, not a chaos-triggered message.

- **Verification**: `_is_valid_json_response()` validates JSON structure and expected fields
- **Failure Mode**: Chaos sends Enter, triggers a response to garbage, we copy that
- **Mitigation**: Check for `guidance`, `action_plan`, `priority` fields; retry if missing
- **Never**: Return a response that doesn't parse as valid JSON with expected schema

### 3. Window State
**INVARIANT**: All UI actions must operate on the correct window (ChatGPT.exe).

- **Verification**: `_ensure_window_viable()` validates hwnd, visibility, and foreground
- **Failure Mode**: Window handle becomes stale (moved/resized/minimized by chaos)
- **Mitigation**: Refresh hwnd, restore from minimized, re-acquire foreground
- **Never**: Click/type into the wrong window

### 4. Focus Continuity
**INVARIANT**: Focus must be on ChatGPT for all UI operations.

- **Verification**: `_ensure_foreground()` with AttachThreadInput technique
- **Failure Mode**: Chaos uses Alt+Tab, clicks Notepad, steals focus
- **Mitigation**: Re-acquire focus before every critical operation
- **Never**: Proceed with action if focus cannot be restored

### 5. Input Field State
**INVARIANT**: Input field must be in correct state before sending prompt.

- **Verification**: `_get_input_button_state()` detects waveform/arrow/stop
- **Failure Mode**: Chaos types garbage, changing state from waveform to arrow
- **Mitigation**: `_clear_input_if_needed()` clears garbage before paste
- **Never**: Paste over existing garbage without clearing first

## Operational Invariants

### 6. Navigation Accuracy
**INVARIANT**: We must click on the correct project and conversation.

- **Verification**: OCR + fuzzy match for text, hover detection for selection
- **Failure Mode**: Chaos scrolls sidebar, click lands on wrong item
- **Mitigation**: Verify post-click via window title or hover detection, retry if wrong
- **Acceptable Risk**: Window title may not match exactly (conversation names can differ)

### 7. Response Completeness
**INVARIANT**: Wait for generation to fully complete before copying.

- **Verification**: Consecutive idle states after generation starts
- **Failure Mode**: Copy mid-generation, get incomplete response
- **Mitigation**: Wait for 3+ consecutive idle readings
- **Never**: Copy while stop button is visible

### 8. Scroll Position
**INVARIANT**: Must be at the bottom of conversation before copying.

- **Verification**: Ctrl+End before copy attempt
- **Failure Mode**: Chaos scrolls up, we copy old message
- **Mitigation**: Force scroll to bottom with Ctrl+End + End×3
- **Never**: Copy without scrolling to bottom first

## Testing Guidelines

### Scenario Matrix
Test across multiple intensities and durations:
- `gentle/30s`, `gentle/60s`
- `medium/30s`, `medium/60s`  
- `aggressive/30s`, `aggressive/60s`

### Deterministic Seeds
Use `--seed=<N>` to reproduce specific failure patterns.

### Phase Logging
Check `[PHASE]` log markers for timing analysis:
```
[PHASE] HH:MM:SS.mmm +elapsed | Step N | phase_name [STATUS]
```

### Failure Analysis
1. Check which invariant was violated
2. Look at phase logs for timing
3. Use seed to reproduce
4. Add specific mitigation if needed

## Escalation Triggers

If an invariant is violated 3+ times with the same pattern:
1. **Document** the failure mode in detail
2. **Escalate** to ChatGPT for architectural guidance
3. **Implement** specific countermeasure
4. **Test** with the same seed to verify fix

## Current Status

| Invariant | Status | Test Coverage |
|-----------|--------|---------------|
| Prompt Integrity | ✓ Implemented | gentle, medium |
| Response Provenance | ✓ Implemented | gentle, medium |
| Window State | ✓ Implemented | gentle, medium |
| Focus Continuity | ✓ Implemented | gentle, medium |
| Input Field State | ✓ Implemented | gentle, medium |
| Navigation Accuracy | ✓ Implemented | gentle |
| Response Completeness | ✓ Implemented | gentle, medium |
| Scroll Position | ✓ Implemented | gentle |
