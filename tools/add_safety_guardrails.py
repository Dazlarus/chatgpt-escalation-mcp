#!/usr/bin/env python3
"""
Add safety guardrails to robust_flow.py by inserting methods after __init__
and replacing click() calls with _safe_click() calls.
"""

def main():
    file_path = r"n:\AI Projects\chatgpt-escalation-mcp\src\drivers\win\robust_flow.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the line after __init__ closes (line 43: "        self._keyboard_fallback_enabled = True")
    insert_after = None
    for i, line in enumerate(lines):
        if 'self._keyboard_fallback_enabled = True' in line:
            insert_after = i + 1
            break
    
    if insert_after is None:
        print("ERROR: Could not find __init__ end marker")
        return 1
    
    # Safety methods to insert
    safety_methods = '''
    # =========================================================================
    # SAFETY GUARDRAILS: Window State & Focus Management
    # =========================================================================

    def _ensure_foreground(self, max_attempts: int = 3) -> bool:
        """
        Ensure ChatGPT window is foreground before UI actions.

        If window has lost focus (e.g., user alt-tabbed), restore it.
        Returns: True if window is foreground, False if failed.
        """
        import win32gui
        import win32con

        for attempt in range(1, max_attempts + 1):
            try:
                # Check current foreground
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd == self.hwnd:
                    return True  # Already foreground

                # Lost focus - restore it
                log_debug(f"  [safety] Window lost focus (attempt {attempt}/{max_attempts}), restoring...")

                # Restore if minimized
                if win32gui.IsIconic(self.hwnd):
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                    time.sleep(0.3)

                # Bring to foreground
                win32gui.SetForegroundWindow(self.hwnd)
                time.sleep(0.2)

                # Verify
                if win32gui.GetForegroundWindow() == self.hwnd:
                    log_debug(f"  [safety] ✓ Focus restored (attempt {attempt})")
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    return True

                # Try BringWindowToTop as fallback
                win32gui.BringWindowToTop(self.hwnd)
                time.sleep(0.2)
                if win32gui.GetForegroundWindow() == self.hwnd:
                    log_debug(f"  [safety] ✓ Focus restored via BringWindowToTop (attempt {attempt})")
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    return True

            except Exception as e:
                log_debug(f"  [safety] Focus restore attempt {attempt} failed: {e}")

            time.sleep(0.3)

        log_debug(f"  [safety] ✗ Could not restore focus after {max_attempts} attempts")
        return False

    def _is_window_ready(self) -> bool:
        """
        Check if window is in a valid state for automation.

        Returns False if:
        - Window is minimized
        - Window is not visible
        - Window handle is invalid
        """
        import win32gui

        try:
            if not self.hwnd:
                log_debug("  [safety] ✗ No window handle")
                return False

            # Check if window still exists
            if not win32gui.IsWindow(self.hwnd):
                log_debug("  [safety] ✗ Window handle is invalid")
                return False

            # Check if minimized
            if win32gui.IsIconic(self.hwnd):
                log_debug("  [safety] ✗ Window is minimized")
                return False

            # Check if visible
            if not win32gui.IsWindowVisible(self.hwnd):
                log_debug("  [safety] ✗ Window is not visible")
                return False

            return True

        except Exception as e:
            log_debug(f"  [safety] ✗ Window state check failed: {e}")
            return False

    def _refresh_hwnd(self) -> bool:
        """
        Refresh window handle if it became invalid.

        Returns: True if hwnd successfully refreshed, False otherwise.
        """
        log_debug("  [safety] Refreshing window handle...")
        hwnd = self._find_chatgpt_hwnd()
        if hwnd:
            self.hwnd = hwnd
            import win32gui
            self.window_rect = win32gui.GetWindowRect(hwnd)
            log_debug(f"  [safety] ✓ Window handle refreshed (hwnd={hwnd})")
            return True
        else:
            log_debug("  [safety] ✗ Could not find ChatGPT window")
            return False

    def _retry_with_recovery(self, operation, operation_name: str, max_attempts: int = 3):
        """
        Retry an operation with window state recovery.

        Args:
            operation: Callable that returns True on success
            operation_name: Name for logging
            max_attempts: Max retry attempts

        Returns: True if operation succeeded, False if all attempts failed
        """
        for attempt in range(1, max_attempts + 1):
            try:
                # Pre-check: ensure window is ready
                if not self._is_window_ready():
                    log_debug(f"  [retry] {operation_name}: Window not ready (attempt {attempt}/{max_attempts})")

                    # Try to refresh handle if invalid
                    if not self.hwnd or not self._is_window_ready():
                        if not self._refresh_hwnd():
                            time.sleep(0.5 * attempt)  # Exponential backoff
                            continue

                    # Try to restore window state
                    import win32gui
                    import win32con
                    if win32gui.IsIconic(self.hwnd):
                        win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                        time.sleep(0.3)

                # Ensure foreground before operation
                if not self._ensure_foreground():
                    log_debug(f"  [retry] {operation_name}: Could not restore focus (attempt {attempt}/{max_attempts})")
                    time.sleep(0.5 * attempt)
                    continue

                # Execute operation
                result = operation()
                if result:
                    if attempt > 1:
                        log_debug(f"  [retry] {operation_name}: ✓ Succeeded on attempt {attempt}")
                    return True
                else:
                    log_debug(f"  [retry] {operation_name}: Operation returned False (attempt {attempt}/{max_attempts})")
                    time.sleep(0.5 * attempt)

            except Exception as e:
                log_debug(f"  [retry] {operation_name}: Exception on attempt {attempt}/{max_attempts}: {e}")
                time.sleep(0.5 * attempt)

        log_debug(f"  [retry] {operation_name}: ✗ Failed after {max_attempts} attempts")
        return False

    def _safe_click(self, x: int, y: int, description: str = "") -> bool:
        """
        Safely click at coordinates with foreground verification.

        Args:
            x, y: Screen coordinates to click
            description: Description for logging

        Returns: True if click succeeded, False if focus lost and couldn't recover
        """
        from pywinauto.mouse import click
        import win32gui

        # Ensure window is foreground before click
        if not self._ensure_foreground():
            log_debug(f"  [safe_click] ✗ Could not ensure foreground for {description}")
            return False

        try:
            click(coords=(x, y))
            log_debug(f"  [safe_click] ✓ Clicked at ({x}, {y}) - {description}")
            return True
        except Exception as e:
            log_debug(f"  [safe_click] ✗ Click failed for {description}: {e}")
            return False

'''
    
    # Insert the safety methods
    lines.insert(insert_after, safety_methods)
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✓ Inserted safety methods after line {insert_after}")
    return 0

if __name__ == "__main__":
    exit(main())
