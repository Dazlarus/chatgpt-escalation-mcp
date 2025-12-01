# Sidebar Selection: OCR + Hover Correction

This driver selects projects in the ChatGPT Desktop sidebar using OCR and validates the selection using pixel‑level hover detection.

Overview
- Step 5 clicks the intended project name using OCR over the sidebar region.
- Immediately after the click, the driver measures the highlighted row via `SidebarHoverDetector`.
- If the highlight does not line up vertically with the click center (> ~18 px), the driver applies a one‑row corrective click up/down (~28 px) and proceeds.
- A secondary verification OCR reads the text nearest to the highlighted row and fuzzy‑matches it against the target.

Why this exists
- OCR box centers can land between rows or text wraps can shift click centers.
- DPI scaling, fonts, or UI updates can cause off‑by‑one row selections.

Logging & Diagnostics
- Set log level to `debug` in config to see detailed flow logs, including:
  - OCR candidates and match scores
  - Click coordinates vs detected highlight center
  - Whether a corrective click was applied
- Logs are emitted on stderr; optionally configure a log file in config.

Tuning constants (advanced)
- File: `src/drivers/win/hover_detection.py`
  - `row_height` (default 35): Approximate row height in pixels.
  - `top_skip` / `bottom_skip`: Pixels to ignore at top/bottom of sidebar.
  - `deviation_threshold`: Minimum brightness deviation to treat a row as highlighted.
- File: `src/drivers/win/robust_flow.py`
  - Corrective click threshold: ~18 px vertical delta before correction.
  - Corrective step: ~28 px (one row). Increase if your UI uses larger rows.

Common issues
- No highlight detected:
  - Ensure the app is in light theme and visible (not covered).
  - Check that the sidebar is open before selection (Step 4).
- Wrong row persists after correction:
  - Increase corrective step from 28 → 32/36.
  - Adjust `row_height` in `hover_detection.py` to better match your UI.
- OCR misses the text:
  - Verify PaddleOCR models are present and loaded.
  - Consider increasing the sidebar OCR region width slightly if truncated.

When to adjust
- If you consistently select one row above/below the target, increase the corrective step.
- If highlight is consistently detected but text matching fails, lower the fuzzy match threshold slightly.

Safe defaults
- The shipped defaults work across typical 100–150% DPI setups in testing.
- Changes should be incremental; capture logs before/after to validate impact.
