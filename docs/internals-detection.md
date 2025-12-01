# Detection Internals

This document explains the low-level detection techniques used by the Windows driver. It’s intended for contributors and advanced users; the README only summarizes high‑level behavior.

## Sidebar State Detection
```
┌─────────────────────────────────┐
│ [X]  ← X button appears here   │
│      when sidebar is open      │
│                                 │
│  Sidebar content...             │
└─────────────────────────────────┘
```
- Samples a ~20×20 pixel region where the close “X” appears when the sidebar is open.
- Counts pixels darker than a brightness threshold (≈100).
- Heuristic:
  - >50 dark pixels → sidebar is OPEN
  - <50 dark pixels → sidebar is CLOSED

## Response Generation Detection
```
┌─────────────────────────────────┐
│                                 │
│  Response text...               │
│                                 │
│           [■ Stop]  ← Stop      │
│                       button    │
└─────────────────────────────────┘
```
- Samples a ~30×30 region near the composer’s right edge where the stop button/waveform appears.
- Counts very dark pixels corresponding to the black stop square.
- Heuristic:
  - 60 < dark pixels < 400 → generating (stop visible)
  - Otherwise → idle/complete
- Polled every 500ms until completion with brief debouncing.

## Copy Button Detection
- Primary: Navigate backwards with Shift+Tab from the input anchor, then validate that the focused element name contains “Copy” before pressing Enter.
- Secondary: UIA fallback enumerates `Button` controls and invokes the one whose name contains “Copy”.
- Last resort: `Ctrl+Shift+C` clipboard copy.

## Sidebar Selection (OCR + Hover)
- OCR (PaddleOCR v5) over the left ~28% of the window finds candidate rows whose text fuzzy‑matches the target.
- After clicking the candidate center, pixel hover detection confirms the highlighted row aligns vertically.
- If the highlight is offset by more than ~18 px, apply a corrective click of ~28 px up/down (approx. one row) and re‑check.
- Optional verification OCR picks the text nearest the highlighted row and re‑matches to the target.

## Tuning
- `src/drivers/win/hover_detection.py`:
  - `row_height`: default 35 px
  - `top_skip` / `bottom_skip`: ignore header/footer bands
  - `deviation_threshold`: minimum brightness deviation to treat a row as highlighted
- `src/drivers/win/robust_flow.py`:
  - Corrective delta threshold: ~18 px
  - Corrective step: ~28 px (≈ one row)

## Limitations
- Assumes light theme and standard ChatGPT Desktop UI geometry.
- DPI scaling and custom fonts may require minor tuning (row height/thresholds).
- UI changes in future ChatGPT releases can affect regions and thresholds.
