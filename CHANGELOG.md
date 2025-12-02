# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-12-02

### Added
- **Structured Observability**
  - Unique `run_id` generated for each escalation (format: `run-{timestamp}-{random}`)
  - Error reason codes for every failure type (e.g., `focus_failed`, `conversation_not_found`, `copy_failed`)
  - Step-level failure tracking - know exactly which step failed and why
  - Failure metadata captured in logs and returned to MCP client

- **Automatic Retry Logic**
  - Up to 4 attempts for any escalation (initial + 3 retries)
  - Intelligent retry detection - most failures are treated as recoverable
  - Fresh state on each retry (kills and restarts ChatGPT)
  - 1.5s pause between retries for stability
  - Empty response detection - retries if response is too short or missing

- **Enhanced Chaos Resilience**
  - Ctrl+K search fallback in step 6 if conversation not found via scroll
  - Antagonist improvements - no longer sends Enter in standard chaos modes (prevents new chat creation)
  - Passes gentle and medium chaos consistently
  - Passes aggressive chaos with retry logic (may need multiple attempts)

- **Better Error Messages**
  - User-facing error messages when all retries exhausted
  - Clear instruction to "keep hands off keyboard/mouse during automation"
  - Detailed failure context for debugging

### Changed
- Retry delay reduced from 3s to 1.5s for faster recovery
- Error handling now distinguishes between recoverable and fatal errors
- `_derive_error_reason()` enhanced to detect empty responses

### Fixed
- Chaos tests now validate that failures are true automation issues, not user interference
- Step 6 (conversation navigation) more robust with Ctrl+K fallback
- Step 10 (copy response) now retries on failure instead of giving up

## [1.0.0] - 2024-11-30

### Added
- **MCP Tools**
  - `escalate_to_expert` - Send questions to ChatGPT Desktop and get responses
  - `list_projects` - Discover available project IDs from configuration

- **Windows Automation** (10-step verified flow)
  - Step 1: Kill ChatGPT (clean state)
  - Step 2: Open ChatGPT (fresh start)
  - Step 3: Focus ChatGPT window
  - Step 4: Open sidebar (hamburger menu)
  - Step 5: Click project folder (with OCR detection)
  - Step 6: Click conversation (with OCR detection)
  - Step 7: Focus text input
  - Step 8: Send prompt
  - Step 9: Wait for response (pixel-based stop button detection)
  - Step 10: Copy response (robust button probing)

- **Detection Systems**
  - Pixel-based sidebar state detection (X button analysis)
  - Pixel-based generation detection (stop button analysis)
  - PaddleOCR v5 integration for text extraction
  - Async OCR model preloading (models load during steps 1-4)
  - Fuzzy string matching for OCR error tolerance

- **Configuration**
  - Project-based conversation mapping
  - Support for project folders in ChatGPT
  - Configurable response timeout
  - Debug logging

### Technical Details
- **Sidebar Detection**: X button pixel check at (x+275, y+58) - >50 dark pixels = open
- **Generation Detection**: Stop button pixel analysis - total>60 AND total<400 = generating
- **Copy Button**: Skip 4 Shift+Tabs (avoid dangerous buttons), then probe each position until clipboard has content
- **OCR**: Bulk OCR on entire sidebar region, find text with bounding boxes, click directly

### Removed
- Vision LLM-based detection (Ollama/llava) - replaced with pixel detection for 100% accuracy
- `chatgpt-desktop-vision` backend type

### Notes
- Vision LLMs (llava, qwen2.5-vl, etc.) achieved only ~67% accuracy for UI detection
- Pixel-based detection achieves 100% accuracy for sidebar and generation state
- PaddleOCR handles text extraction reliably with fuzzy matching for error tolerance
