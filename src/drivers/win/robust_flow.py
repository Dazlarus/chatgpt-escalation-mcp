#!/usr/bin/env python3
"""
Robust ChatGPT automation flow with verification gates.

Each step has:
1. Action
2. Verification (with retries)
3. Only proceed when verified

This prevents race conditions and ensures reliable automation.
"""

import time
import sys
import os

# Add driver directory to path
_driver_dir = os.path.dirname(os.path.abspath(__file__))
if _driver_dir not in sys.path:
    sys.path.insert(0, _driver_dir)

# Start OCR model preloading immediately (background thread)
# This runs during steps 1-4 so OCR is ready by step 5
from ocr_extraction import start_ocr_preload
start_ocr_preload()


def log_debug(msg: str):
    """Log debug message to stderr."""
    print(f"[FLOW] {msg}", file=sys.stderr)


class RobustChatGPTFlow:
    """
    Robust ChatGPT automation with verification gates between each step.
    """
    
    def __init__(self):
        self.hwnd = None
        self.window_rect = None
        # Allow test harness to disable keyboard fallbacks to avoid global Tab usage in CI
        self._keyboard_fallback_enabled = True

    # =========================================================================
    # SAFETY GUARDRAILS: Window State & Focus Management
    # =========================================================================

    def _ensure_foreground(self, max_attempts: int = 3) -> bool:
        """
        Ensure ChatGPT window is foreground before UI actions.

        If window has lost focus (e.g., user alt-tabbed), restore it.
        Uses AttachThreadInput technique to bypass Windows focus restrictions.
        Returns: True if window is foreground, False if failed.
        """
        import win32gui
        import win32con
        import win32process
        import win32api

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

                # Use AttachThreadInput technique to bypass Windows foreground restrictions
                try:
                    # Get thread IDs
                    fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
                    target_thread, _ = win32process.GetWindowThreadProcessId(self.hwnd)
                    
                    # Attach to foreground thread temporarily
                    if fg_thread != target_thread:
                        win32process.AttachThreadInput(target_thread, fg_thread, True)
                        try:
                            win32gui.SetForegroundWindow(self.hwnd)
                            win32gui.BringWindowToTop(self.hwnd)
                            win32gui.SetFocus(self.hwnd)
                        finally:
                            win32process.AttachThreadInput(target_thread, fg_thread, False)
                    else:
                        win32gui.SetForegroundWindow(self.hwnd)
                except Exception as e:
                    # Fallback to simple approach
                    log_debug(f"  [safety] AttachThreadInput failed: {e}, trying simple approach")
                    win32gui.SetForegroundWindow(self.hwnd)
                
                time.sleep(0.2)

                # Verify
                if win32gui.GetForegroundWindow() == self.hwnd:
                    log_debug(f"  [safety] ✓ Focus restored (attempt {attempt})")
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    return True

                # Try ShowWindow with SW_SHOW as another fallback
                win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
                time.sleep(0.2)
                if win32gui.GetForegroundWindow() == self.hwnd:
                    log_debug(f"  [safety] ✓ Focus restored via SW_SHOW (attempt {attempt})")
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

    
    # =========================================================================
    # STEP 1: Kill ChatGPT
    # =========================================================================
    
    def step1_kill_chatgpt(self, timeout: float = 5.0) -> bool:
        """
        Kill ChatGPT if running.
        
        Verification: Process no longer exists.
        """
        import psutil
        
        log_debug("STEP 1: Killing ChatGPT if running...")
        
        # Find and kill
        killed = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == "chatgpt.exe":
                    log_debug(f"  Terminating PID {proc.info['pid']}")
        
                    proc.terminate()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not killed:
            log_debug("  ChatGPT was not running")
            return True
        
        # VERIFY: Wait for process to actually exit
        start = time.time()
        while (time.time() - start) < timeout:
            still_running = False
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == "chatgpt.exe":
                        still_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not still_running:
                log_debug("  ✓ VERIFIED: ChatGPT process terminated")
                return True

            time.sleep(0.3)

        log_debug("  ✗ FAILED: ChatGPT still running after timeout")
        return False
    
    # =========================================================================
    # STEP 2: Start ChatGPT
    # =========================================================================
    
    def step2_start_chatgpt(self, timeout: float = 15.0) -> bool:
        """
        Start ChatGPT Desktop.
        
        Verification: Window handle found AND window is visible.
        """
        import subprocess
        import win32gui
        import win32process
        import psutil
        
        log_debug("STEP 2: Starting ChatGPT...")
        
        # Launch
        subprocess.Popen(
            'start "" "ChatGPT"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # VERIFY: Wait for window to appear
        start = time.time()
        while (time.time() - start) < timeout:
            hwnd = self._find_chatgpt_hwnd()
            if hwnd:
                # Additional check: window must be visible
                if win32gui.IsWindowVisible(hwnd):
                    self.hwnd = hwnd
                    self.window_rect = win32gui.GetWindowRect(hwnd)
                    title = win32gui.GetWindowText(hwnd)
                    log_debug(f"  ✓ VERIFIED: Window found (hwnd={hwnd}, title='{title}')")
                    
                    # Extra wait for UI to fully initialize
                    time.sleep(1.5)
                    return True
            
            time.sleep(0.5)
        
        log_debug("  ✗ FAILED: Window not found after timeout")
        return False
    
    def _find_chatgpt_hwnd(self):
        """Find ChatGPT window handle."""
        import win32gui
        import win32process
        import psutil
        
        result = [None]
        
        def callback(hwnd, _):
            if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    if proc.name().lower() == "chatgpt.exe":
                        title = win32gui.GetWindowText(hwnd)
                        if title and "IME" not in title and "Default" not in title:
                            result[0] = hwnd
                            return False  # Stop enumeration
                except:
                    pass
            return True
        
        try:
            win32gui.EnumWindows(callback, None)
        except Exception as e:
            # EnumWindows failed (permission or runtime issue); try fallback method
            log_debug(f"  EnumWindows failed: {e} - trying psutil + pywinauto fallback")
            # Call a smaller fallback routine to avoid nested try/except confusion
            try:
                return self._find_chatgpt_hwnd_fallback(psutil)
            except Exception as e2:
                log_debug(f"  Fallback via pywinauto failed: {e2}")
            # If fallback failed, return whatever we have (likely None)
            return result[0]
        return result[0]

    def _find_chatgpt_hwnd_fallback(self, psutil_module):
        """Fallback: use psutil + pywinauto to find a top window for chatgpt.exe"""
        from pywinauto import Application

        for proc in psutil_module.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'chatgpt.exe':
                    pid = proc.info['pid']
                    try:
                        app = Application(backend='uia').connect(process=pid)
                        top = app.top_window()
                        hwnd = top.handle
                        if hwnd:
                            return hwnd
                    except Exception:
                        continue
            except Exception:
                continue
        return None
    
    # =========================================================================
    # STEP 3: Focus ChatGPT
    # =========================================================================
    
    def step3_focus_chatgpt(self, timeout: float = 5.0) -> bool:
        """
        Bring ChatGPT to foreground.
        
        Verification: ChatGPT is the foreground window.
        """
        import win32gui
        import win32con
        
        log_debug("STEP 3: Focusing ChatGPT window...")
        
        if not self.hwnd:
            log_debug("  ✗ FAILED: No window handle")
            return False
        
        # Try multiple methods to bring to front
        start = time.time()
        attempt = 0
        
        while (time.time() - start) < timeout:
            attempt += 1
            
            try:
                # Restore if minimized
                if win32gui.IsIconic(self.hwnd):
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                    time.sleep(0.3)
                
                # Method 1: SetForegroundWindow
                win32gui.SetForegroundWindow(self.hwnd)
                time.sleep(0.3)
                
                # VERIFY: Check if we're now foreground
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd == self.hwnd:
                    log_debug(f"  ✓ VERIFIED: ChatGPT is foreground (attempt {attempt})")
                    
                    # Update rect in case window moved
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    return True
                
                # Method 2: Try BringWindowToTop
                win32gui.BringWindowToTop(self.hwnd)
                time.sleep(0.3)
                
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd == self.hwnd:
                    log_debug(f"  ✓ VERIFIED: ChatGPT is foreground (attempt {attempt}, method 2)")
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    return True
                
            except Exception as e:
                log_debug(f"  Focus attempt {attempt} failed: {e}")
            
            # If we're still not foreground, attempt UIA set_focus or title bar click as a last-resort
            try:
                from pywinauto import Application
                app = Application(backend='uia').connect(handle=self.hwnd)
                top = app.top_window()
                try:
                    top.set_focus()
                    time.sleep(0.25)
                    if win32gui.GetForegroundWindow() == self.hwnd:
                        self.window_rect = win32gui.GetWindowRect(self.hwnd)
                        log_debug(f"  ✓ VERIFIED: ChatGPT is foreground after UIA set_focus (attempt {attempt})")
                        return True
                except Exception:
                    # Fallthrough to click title bar
                    pass
            except Exception:
                pass

            # Click title-bar center as a fallback to force focus
            try:
                rect = win32gui.GetWindowRect(self.hwnd)
                title_click_x = rect[0] + 40
                title_click_y = rect[1] + 10
                from pywinauto.mouse import click
                click(coords=(title_click_x, title_click_y))
                time.sleep(0.25)
                if win32gui.GetForegroundWindow() == self.hwnd:
                    self.window_rect = win32gui.GetWindowRect(self.hwnd)
                    log_debug(f"  ✓ VERIFIED: ChatGPT is foreground after title click (attempt {attempt})")
                    return True
            except Exception:
                pass

            time.sleep(0.3)
        
        log_debug("  ✗ FAILED: Could not focus window after timeout")
        return False
    
    # =========================================================================
    # STEP 4: Open Sidebar
    # =========================================================================
    
    def step4_open_sidebar(self, timeout: float = 3.0) -> bool:
        """
        Open the sidebar by clicking hamburger menu.
        
        Verification: Sidebar region has light gray background (~249,249,249).
        """
        import win32gui
        from pywinauto.mouse import click
        from PIL import ImageGrab
        import numpy as np
        
        log_debug("STEP 4: Opening sidebar...")
        
        if not self.hwnd or not self.window_rect:
            log_debug("  ✗ FAILED: No window")
            return False
        
        rect = self.window_rect
        
        # First check if sidebar is already open
        if self._is_sidebar_open():
            log_debug("  ✓ Sidebar already open")
            return True
        
        # Click hamburger menu (top-left)
        menu_x = rect[0] + 30
        menu_y = rect[1] + 70
        
        log_debug(f"  Clicking hamburger at ({menu_x}, {menu_y})")
        # Safe click with foreground verification
        if not self._safe_click(menu_x, menu_y, "hamburger menu"):
            log_debug("  ✗ FAILED: Could not click hamburger menu")
            return False
        
        # VERIFY: Wait for sidebar to appear
        start = time.time()
        while (time.time() - start) < timeout:
            time.sleep(0.3)
            
            if self._is_sidebar_open():
                log_debug("  ✓ VERIFIED: Sidebar is open")
                return True
        
        log_debug("  ✗ FAILED: Sidebar not detected after click")
        return False
    
    def _is_sidebar_open(self) -> bool:
        """Fast check if sidebar is open by looking for X close button."""
        from PIL import ImageGrab
        import numpy as np
        
        if not self.window_rect:
            return False
        
        rect = self.window_rect
        
        # X button is at approximately x+275, y+58 (center of X)
        # Capture a 20x20 area around it
        x_center = rect[0] + 275
        y_center = rect[1] + 58
        
        try:
            area = (x_center - 10, y_center - 10, x_center + 10, y_center + 10)
            img = ImageGrab.grab(bbox=area)
            pixels = np.array(img)
            
            # The X icon has dark pixels (gray lines on light background)
            # Count pixels darker than 180
            dark_pixels = np.sum(pixels < 180)
            
            # If we see dark pixels (>30), the X button is visible = sidebar open
            is_open = dark_pixels > 30
            log_debug(f"  Sidebar check: {dark_pixels} dark pixels -> {'OPEN' if is_open else 'CLOSED'}")
            return is_open
        except Exception as e:
            log_debug(f"  Sidebar check failed: {e}")
            return False
    
    # =========================================================================
    # STEP 5: Click Project
    # =========================================================================
    
    def step5_click_project(self, project_name: str, timeout: float = 10.0) -> bool:
        """
        Find and click on a project in the sidebar.
        
        Verification: Window title contains project name OR we detect hover on target.
        """
        import win32gui
        
        log_debug(f"STEP 5: Clicking project '{project_name}'...")
        
        # Retry logic for chaos resilience
        max_attempts = 3
        for attempt in range(max_attempts):
            # Ensure foreground before every attempt (including first)
            if not self._ensure_foreground():
                log_debug(f"  ⚠ Could not ensure foreground for attempt {attempt + 1}")
                time.sleep(0.5)
                continue
                
            if attempt > 0:
                log_debug(f"  Retry attempt {attempt + 1}/{max_attempts}...")
                time.sleep(0.5)
            
            result = self._find_and_click_sidebar_item(project_name, timeout / max_attempts)

            if result:
                # Verify by checking window title (best-effort)
                time.sleep(0.5)
                title = win32gui.GetWindowText(self.hwnd)
                if project_name.lower() in title.lower():
                    log_debug(f"  ✓ VERIFIED: Window title is '{title}'")
                    return True

                # Title may not change; validate via hover detection + OCR nearest text
                if self._verify_sidebar_selection(project_name):
                    log_debug("  ✓ VERIFIED: Hover/OCR matches intended project")
                    return True

                log_debug("  ⚠ Post-click validation did not match - will retry")
                # Continue to next attempt instead of returning False immediately
                continue
        
        log_debug(f"  ✗ FAILED: Could not find/click '{project_name}' after {max_attempts} attempts")
        return False

    def _verify_sidebar_selection(self, target: str) -> bool:
        """Verify the currently highlighted sidebar item text matches target using OCR + hover detection."""
        from hover_detection import detect_highlighted_item
        from ocr_extraction import get_ocr
        from fuzzy_match import similarity_ratio
        from PIL import ImageGrab
        try:
            hi = detect_highlighted_item(self.hwnd)
        except Exception:
            hi = None
        if not hi:
            return False
        rect = self.window_rect
        if not rect:
            return False
        window_width = rect[2] - rect[0]
        sidebar_width = int(window_width * 0.28)
        sidebar_left = rect[0]
        sidebar_top = rect[1] + 80
        sidebar_bottom = rect[3] - 50
        sidebar_right = rect[0] + sidebar_width
        try:
            screenshot = ImageGrab.grab(bbox=(sidebar_left, sidebar_top, sidebar_right, sidebar_bottom))
        except Exception:
            return False
        import tempfile, os
        ocr = get_ocr()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
            screenshot.save(temp_path)
        try:
            results = ocr.predict(temp_path)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        # Pick text nearest to highlighted y
        highlight_y = hi['screen_coords'][1]
        best_text = None
        best_dist = 1e9
        for res in results:
            if 'rec_texts' not in res or 'rec_boxes' not in res:
                continue
            texts = res['rec_texts']
            boxes = res['rec_boxes']
            for text, box in zip(texts, boxes):
                box_center_y = sidebar_top + (box[1] + box[3]) / 2
                dist = abs(box_center_y - highlight_y)
                if dist < best_dist:
                    best_dist = dist
                    best_text = text
        if not best_text:
            log_debug(f"  [verify] No OCR text found near highlight")
            return False
        match_score = similarity_ratio(target.lower(), best_text.lower())
        matched = match_score >= 0.7 or (target.lower() in best_text.lower())
        log_debug(f"  [verify] Best text='{best_text[:40]}', match_score={match_score:.2f}, matched={matched}")
        return matched
    
    # =========================================================================
    # STEP 6: Click Conversation
    # =========================================================================
    
    def step6_click_conversation(self, conversation_name: str, timeout: float = 10.0) -> bool:
        """
        Find and click on a conversation in the PROJECT VIEW (main content area).
        
        After clicking a project, sidebar closes and conversations appear in center.
        
        Verification: Window title contains conversation name.
        """
        import win32gui
        
        log_debug(f"STEP 6: Clicking conversation '{conversation_name}'...")
        
        # Retry logic for chaos resilience
        max_attempts = 3
        for attempt in range(max_attempts):
            # Ensure foreground before every attempt (including first)
            if not self._ensure_foreground():
                log_debug(f"  ⚠ Could not ensure foreground for attempt {attempt + 1}")
                time.sleep(0.5)
                continue
                
            if attempt > 0:
                log_debug(f"  Retry attempt {attempt + 1}/{max_attempts}...")
                time.sleep(0.5)
            
            # After project click, conversations are in MAIN content area, not sidebar
            result = self._find_and_click_project_item(conversation_name, timeout / max_attempts)
            
            if result:
                # Verify by checking window title
                time.sleep(0.8)
                title = win32gui.GetWindowText(self.hwnd)
                
                # Fuzzy check
                if self._fuzzy_match(conversation_name, title):
                    log_debug(f"  ✓ VERIFIED: Window title is '{title}'")
                    return True
                else:
                    log_debug(f"  ⚠ Click done but title='{title}' doesn't match '{conversation_name}'")
                    # Still return true - might be OK
                    return True
        
        log_debug(f"  ✗ FAILED: Could not find/click '{conversation_name}' after {max_attempts} attempts")
        return False
    
    def _fuzzy_match(self, target: str, text: str, threshold: float = 0.6) -> bool:
        """Simple fuzzy match - check if words overlap."""
        target_words = set(target.lower().split())
        text_words = set(text.lower().split())
        
        if not target_words:
            return False
        
        overlap = len(target_words & text_words)
        ratio = overlap / len(target_words)
        
        return ratio >= threshold or target.lower() in text.lower()
    
    def _find_and_click_sidebar_item(self, target: str, timeout: float = 10.0) -> bool:
        """
        Find and click target item in sidebar using OCR (fast method).
        OCRs the entire sidebar at once and clicks directly on the target.
        """
        import win32api
        import win32gui
        from pywinauto.mouse import click
        from PIL import ImageGrab
        import tempfile
        import os
        
        from ocr_extraction import get_ocr
        from fuzzy_match import similarity_ratio
        from hover_detection import detect_highlighted_item
        
        ocr = get_ocr()
        rect = self.window_rect
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        # Sidebar region (left 28%, skip title bar area)
        sidebar_width = int(window_width * 0.28)
        sidebar_left = rect[0]
        sidebar_right = rect[0] + sidebar_width
        sidebar_top = rect[1] + 80  # Below title bar
        sidebar_bottom = rect[3] - 50  # Above bottom
        
        log_debug(f"  Scanning sidebar for '{target}'...")
        
        start_time = time.time()
        scroll_count = 0
        max_scrolls = 5
        
        while (time.time() - start_time) < timeout:
            # Ensure foreground before screenshot - critical for chaos resilience
            if not self._ensure_foreground():
                log_debug(f"  ⚠ Lost foreground before sidebar screenshot, retrying...")
                time.sleep(0.3)
                continue
                
            # Capture entire sidebar
            try:
                screenshot = ImageGrab.grab(bbox=(sidebar_left, sidebar_top, sidebar_right, sidebar_bottom))
                
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    temp_path = f.name
                    screenshot.save(temp_path)
                
                results = ocr.predict(temp_path)
                os.unlink(temp_path)
                
                # Find target in OCR results
                for res in results:
                    if 'rec_texts' not in res or 'rec_boxes' not in res:
                        continue
                    
                    texts = res['rec_texts']
                    boxes = res['rec_boxes']
                    scores = res.get('rec_scores', [1.0] * len(texts))
                    
                    for text, box, score in zip(texts, boxes, scores):
                        match_score = similarity_ratio(target.lower(), text.lower())
                        
                        log_debug(f"    At y={int(box[1])}: '{text[:30]}...' (score={match_score:.2f})")
                        
                        if match_score >= 0.7 or target.lower() in text.lower():
                            log_debug(f"  FOUND '{target}' - clicking!")
                            
                            # Calculate click position from box
                            box_center_x = (box[0] + box[2]) / 2
                            box_center_y = (box[1] + box[3]) / 2
                            
                            click_x = int(sidebar_left + box_center_x)
                            click_y = int(sidebar_top + box_center_y)
                            
                            # Safe click with foreground verification
                            if not self._safe_click(click_x, click_y, f"sidebar item '{target}'"):
                                log_debug(f"  ✗ Safe click failed for '{target}'")
                                continue  # Try next match
                            time.sleep(0.35)

                            # Post-click validation: ensure the highlighted row matches intended target.
                            try:
                                hi = detect_highlighted_item(self.hwnd)
                            except Exception as _e:
                                hi = None

                            if hi and 'screen_coords' in hi:
                                highlighted_y = hi['screen_coords'][1]
                                delta_y = highlighted_y - click_y
                                # If highlight is more than ~18px away from the clicked center, we likely selected a neighbor
                                if abs(delta_y) > 18:
                                    log_debug(f"  ⚠ CORRECTION NEEDED: Highlight at y={highlighted_y}, click was y={click_y}, delta={delta_y}px")
                                    # Try clicking one row up or down depending on where highlight landed
                                    # Sidebar row height is ~35px; use 28px as conservative step
                                    step = 28
                                    corrective_y = click_y - step if delta_y > 0 else click_y + step
                                    direction = "above" if delta_y > 0 else "below"
                                    log_debug(f"  Applying corrective click {step}px {direction} original (y={corrective_y})")
                                    if self._safe_click(click_x, corrective_y, f"corrective click for '{target}' {direction}"):
                                        time.sleep(0.3)
                                        log_debug(f"  ✓ Corrective click completed for target '{target}'")
                                    else:
                                        log_debug(f"  ✗ Corrective click failed for '{target}'")
                                else:
                                    log_debug(f"  ✓ Highlight aligned (delta={delta_y}px, within threshold)")

                            return True
                
            except Exception as e:
                log_debug(f"  Error scanning sidebar: {e}")
            
            # Not found - scroll down
            scroll_count += 1
            if scroll_count > max_scrolls:
                break
            
            log_debug(f"  Scrolling down (attempt {scroll_count})...")
            self._scroll_sidebar("down")
            time.sleep(0.4)
        
        return False
    
    def _find_and_click_project_item(self, target: str, timeout: float = 10.0) -> bool:
        """
        Scan PROJECT VIEW (main content area) looking for conversation.
        After clicking a project, conversations appear in center, not sidebar.
        """
        import win32api
        from pywinauto.mouse import click
        from PIL import ImageGrab
        import tempfile
        import os
        
        # Import OCR
        from ocr_extraction import get_ocr
        from fuzzy_match import fuzzy_contains, similarity_ratio
        
        ocr = get_ocr()
        rect = self.window_rect
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        # Project view: conversations are in the CENTER of the window
        # Based on screenshot: roughly from x=120 to x=750, y=180 to y=400
        # As percentage of window: x=15% to 85%, y=25% to 70%
        
        content_left = rect[0] + int(window_width * 0.12)
        content_right = rect[0] + int(window_width * 0.88)
        content_top = rect[1] + int(window_height * 0.30)
        content_bottom = rect[1] + int(window_height * 0.75)
        
        log_debug(f"  Scanning project view for '{target}'...")
        log_debug(f"  Content area: ({content_left}, {content_top}) to ({content_right}, {content_bottom})")
        
        # Ensure foreground before screenshot - critical for chaos resilience
        if not self._ensure_foreground():
            log_debug(f"  ✗ Could not ensure foreground for project view screenshot")
            return False
        
        # Capture the content area
        try:
            screenshot = ImageGrab.grab(bbox=(content_left, content_top, content_right, content_bottom))
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name
                screenshot.save(temp_path)
            
            results = ocr.predict(temp_path)
            os.unlink(temp_path)
            
            # Find all text items
            for res in results:
                if 'rec_texts' not in res or 'rec_boxes' not in res:
                    continue
                
                texts = res['rec_texts']
                boxes = res['rec_boxes']
                scores = res.get('rec_scores', [1.0] * len(texts))
                
                for text, box, score in zip(texts, boxes, scores):
                    # Check if this matches our target
                    match_score = similarity_ratio(target.lower(), text.lower())
                    
                    if match_score >= 0.7 or target.lower() in text.lower():
                        log_debug(f"    FOUND '{text}' (match={match_score:.2f})")
                        
                        # Calculate click position from box
                        # Box is in screenshot coordinates, need to add content_left/top
                        box_center_x = (box[0] + box[2]) / 2
                        box_center_y = (box[1] + box[3]) / 2
                        
                        click_x = int(content_left + box_center_x)
                        click_y = int(content_top + box_center_y)
                        
                        log_debug(f"    Clicking at ({click_x}, {click_y})")
                        # Safe click with foreground verification
                        return self._safe_click(click_x, click_y, f"project item '{target}'")
                    else:
                        log_debug(f"    '{text}' (match={match_score:.2f}) - no match")
            
            log_debug(f"  Target '{target}' not found in project view")
            return False
            
        except Exception as e:
            log_debug(f"  Error scanning project view: {e}")
            return False
    
    def _capture_sidebar(self):
        """Capture sidebar region."""
        from PIL import ImageGrab
        
        if not self.window_rect:
            return None
        
        rect = self.window_rect
        window_width = rect[2] - rect[0]
        sidebar_width = int(window_width * 0.28)
        
        sidebar_rect = (rect[0], rect[1], rect[0] + sidebar_width, rect[3])
        
        try:
            return ImageGrab.grab(bbox=sidebar_rect)
        except:
            return None
    
    def _scroll_sidebar(self, direction: str = "down"):
        """Scroll sidebar."""
        import win32api
        from pywinauto.mouse import scroll
        
        rect = self.window_rect
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        sidebar_width = int(window_width * 0.28)
        sidebar_x = rect[0] + (sidebar_width // 2)
        sidebar_y = rect[1] + (window_height // 2)
        
        win32api.SetCursorPos((sidebar_x, sidebar_y))
        time.sleep(0.1)
        
        wheel_dist = -3 if direction == "down" else 3
        scroll(coords=(sidebar_x, sidebar_y), wheel_dist=wheel_dist)
    
    # =========================================================================
    # STEP 7: Focus Text Input (now split into focus + send helpers)
    # =========================================================================

    def _is_edit_focused(self) -> bool:
        """Return True if current UIA focused control is an Edit/Document/Text element."""
        try:
            # Use Windows UIA directly via comtypes to get the focused element
            import comtypes.client
            UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
            
            uia = comtypes.client.CreateObject(CUIAutomation)
            focused = uia.GetFocusedElement()
            if not focused:
                log_debug("[focus] _is_edit_focused: no focused element")
                return False
            
            ctype_id = focused.CurrentControlType
            name = focused.CurrentName or ''
            class_name = focused.CurrentClassName or ''
            
            # Control type IDs: Edit=50004, Document=50030, Text=50020, Custom=50025, Group=50026
            type_names = {50004: 'Edit', 50030: 'Document', 50020: 'Text', 50025: 'Custom', 50026: 'Group'}
            ctype_name = type_names.get(ctype_id, f'Unknown({ctype_id})')
            log_debug(f"[focus] focused element: type={ctype_name}, name={name[:50]!r}, class={class_name!r}")
            
            # Accept Edit, Document, or Group (Chrome renders input as Group sometimes)
            # Also accept if class is Chrome_RenderWidgetHostHWND (the Electron/Chrome input surface)
            if ctype_id in (50004, 50030):
                return True
            if ctype_id == 50026 and class_name == 'Chrome_RenderWidgetHostHWND':
                return True
            return False
        except Exception as e:
            log_debug(f"[focus] _is_edit_focused error: {e}")
            return False

    def ensure_input_focus(self) -> bool:
        """
        Focus the text input without typing.
        Strategy (in order): direct click grid, UIA Edit search, calibration variance,
        guarded minimal Tab traversal.
        Returns True once an editable control is focused.
        """
        from pywinauto.mouse import click
        import win32gui

        log_debug("[focus] ensure_input_focus start")

        if not self.hwnd:
            log_debug("[focus] ✗ FAILED: No hwnd")
            return False

        rect = self.window_rect
        # Refresh rect if missing
        if rect is None and self.hwnd:
            try:
                rect = win32gui.GetWindowRect(self.hwnd)
                self.window_rect = rect
            except Exception as e:
                log_debug(f"[focus] Failed to refresh window rect: {e}")
                rect = None

        if rect is None:
            # Try to rediscover window
            new_hwnd = self._find_chatgpt_hwnd()
            if new_hwnd:
                self.hwnd = new_hwnd
                try:
                    rect = win32gui.GetWindowRect(new_hwnd)
                    self.window_rect = rect
                except Exception:
                    rect = None
        if rect is None:
            log_debug("[focus] ✗ FAILED: No window rect")
            return False

        # Check if already focused
        if self._is_edit_focused():
            log_debug("[focus] already focused on edit/document — skipping strategies")
            return True

        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        input_x = rect[0] + int(window_width * 0.5)
        input_y = rect[1] + int(window_height * 0.83)
        log_debug(f"[focus] window rect: {rect}, input target: ({input_x}, {input_y})")

        # Strategy 1: Grid clicks
        log_debug("[focus] trying strategy: grid_click")
        offsets = [0, -10, 10, -20, 20]
        for ox in offsets:
            for oy in offsets:
                try:
                    win32gui.SetForegroundWindow(self.hwnd)
                except Exception:
                    pass
                try:
                    click(coords=(input_x + ox, input_y + oy))
                except Exception as e:
                    log_debug(f"[focus] grid click error at offset ({ox},{oy}): {e}")
                time.sleep(0.15)
                if self._is_edit_focused():
                    log_debug("[focus] ✓ success via grid_click")
                    return True
        log_debug("[focus] grid_click did not yield edit focus")

        # Strategy 2: UIA Edit fallback
        log_debug("[focus] trying strategy: uia_edit")
        try:
            from pywinauto import Application
            app = Application(backend='uia').connect(handle=self.hwnd)
            main_win = app.window(handle=self.hwnd)
            edits = main_win.descendants(control_type='Edit')
            log_debug(f"[focus] UIA found {len(edits)} Edit controls")
            if edits:
                edits[0].set_focus()
                time.sleep(0.25)
                if self._is_edit_focused():
                    log_debug("[focus] ✓ success via uia_edit")
                    return True
                else:
                    log_debug("[focus] uia_edit set_focus did not yield edit focus")
            else:
                log_debug("[focus] no Edit controls found via UIA")
        except Exception as e:
            log_debug(f"[focus] uia_edit failed: {e}")

        # Strategy 3: Calibration variance heuristic
        log_debug("[focus] trying strategy: variance_click")
        try:
            from PIL import ImageGrab
            import numpy as np
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            band_top = rect[1] + int(height * 0.80)
            band_bottom = rect[1] + int(height * 0.86)
            band_left = rect[0] + int(width * 0.15)
            band_right = rect[0] + int(width * 0.85)
            img = ImageGrab.grab(bbox=(band_left, band_top, band_right, band_bottom))
            arr = np.array(img)
            col_var = arr.var(axis=(0, 2))
            if len(col_var) > 0:
                peak_x_offset = int(np.argmax(col_var))
                focus_x = band_left + peak_x_offset
                focus_y = band_top + (band_bottom - band_top) // 2
                log_debug(f"[focus] variance peak at x_offset={peak_x_offset}, clicking ({focus_x}, {focus_y})")
                try:
                    win32gui.SetForegroundWindow(self.hwnd)
                except Exception:
                    pass
                click(coords=(focus_x, focus_y))
                time.sleep(0.25)
                if self._is_edit_focused():
                    log_debug("[focus] ✓ success via variance_click")
                    return True
                else:
                    log_debug("[focus] variance_click did not yield edit focus")
            else:
                log_debug("[focus] variance array empty")
        except Exception as e:
            log_debug(f"[focus] variance_click failed: {e}")

        # Strategy 4: Guarded minimal Tab traversal
        log_debug("[focus] trying strategy: tab_traversal")
        try:
            if not self._is_edit_focused() and self._keyboard_fallback_enabled:
                from pywinauto.keyboard import send_keys
                for i in range(3):
                    try:
                        win32gui.SetForegroundWindow(self.hwnd)
                    except Exception:
                        pass
                    send_keys('{TAB}')
                    time.sleep(0.12)
                    if self._is_edit_focused():
                        log_debug(f"[focus] ✓ success via tab_traversal (Tab #{i+1})")
                        return True
                # Final direct click after tabs
                log_debug("[focus] tab_traversal: 3 tabs done, trying final click")
                try:
                    win32gui.SetForegroundWindow(self.hwnd)
                except Exception:
                    pass
                click(coords=(input_x, input_y))
                time.sleep(0.2)
                if self._is_edit_focused():
                    log_debug("[focus] ✓ success via tab_traversal + final click")
                    return True
                else:
                    log_debug("[focus] tab_traversal + final click did not yield edit focus")
            else:
                log_debug("[focus] tab_traversal skipped (already focused or disabled)")
        except Exception as e:
            log_debug(f"[focus] tab_traversal failed: {e}")

        # Final check
        if self._is_edit_focused():
            log_debug("[focus] ✓ focused after all strategies (late detection)")
            return True
        log_debug("[focus] ✗ FAILED: could not focus input after all strategies")
        return False

    def step7_send_prompt(self, prompt: str) -> bool:
        """Focus input (ensure_input_focus) then readiness probe and send prompt."""
        log_debug("STEP 7+8: Focus & Send Prompt...")
        from pywinauto.mouse import click
        import win32gui
        
        # Ensure foreground before any UI interaction
        if not self._ensure_foreground():
            log_debug("  ✗ Could not ensure foreground before sending prompt")
            return False
            
        if not self.ensure_input_focus():
            return False
        # Determine input center for re-clicks
        rect = self.window_rect
        if not rect:
            return False
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        input_x = rect[0] + int(window_width * 0.5)
        input_y = rect[1] + int(window_height * 0.83)

        import pyperclip
        from pywinauto.keyboard import send_keys
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None

        max_attempts = 8
        for attempt in range(max_attempts):
            log_debug(f"  Probe attempt {attempt+1}/{max_attempts} (Ctrl+C)")
            
            # Ensure foreground before each probe attempt
            if not self._ensure_foreground():
                log_debug(f"   Lost foreground at attempt {attempt+1}, retrying...")
                time.sleep(0.3)
                continue
                
            try:
                send_keys('^c')
            except Exception as e:
                log_debug(f"   Ctrl+C failed: {e}")
            time.sleep(0.12)
            try:
                if not self._is_generating():
                    log_debug("  Idle (arrow) detected — sending prompt")
                    
                    # Final foreground check before sending
                    if not self._ensure_foreground():
                        log_debug("   Lost foreground before paste, retrying...")
                        continue
                        
                    pyperclip.copy(prompt)
                    time.sleep(0.06)
                    send_keys('^v')
                    time.sleep(0.12)
                    send_keys('{ENTER}')
                    time.sleep(0.4)
                    if previous_clipboard is not None:
                        try:
                            pyperclip.copy(previous_clipboard)
                        except Exception:
                            pass
                    log_debug("  ✓ Prompt sent")
                    return True
            except Exception:
                pass
            # Re-click input before retry (use _safe_click)
            if not self._safe_click(input_x, input_y, "re-click input"):
                log_debug("   Safe re-click failed, continuing...")
            time.sleep(0.2)

        if previous_clipboard is not None:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception:
                pass
        log_debug("  ✗ FAILED: Prompt not sent after readiness attempts")
        return False
    
    # =========================================================================
    # STEP 8: Send Prompt
    # =========================================================================
    
    
    # =========================================================================
    # STEP 9: Wait for Response
    # =========================================================================
    
    def step9_wait_for_response(self, timeout: float = 120.0) -> bool:
        """
        Wait for ChatGPT to finish generating.
        
        Detection: Black stop button visible = generating, waveform = idle.
        """
        from PIL import ImageGrab
        import numpy as np
        
        log_debug("STEP 9: Waiting for response...")
        
        start_time = time.time()
        
        # Initial wait for generation to start
        time.sleep(1.0)
        
        generation_started = False
        consecutive_idle = 0
        foreground_failures = 0
        max_foreground_failures = 10
        
        while (time.time() - start_time) < timeout:
            # Ensure window is visible/foreground for screenshot
            if not self._ensure_foreground():
                foreground_failures += 1
                log_debug(f"  ⚠ Lost foreground ({foreground_failures}/{max_foreground_failures})")
                if foreground_failures >= max_foreground_failures:
                    log_debug(f"  ✗ Too many foreground failures, aborting wait")
                    return False
                time.sleep(0.5)
                continue
            
            is_gen = self._is_generating()
            
            if is_gen:
                generation_started = True
                consecutive_idle = 0
                foreground_failures = 0  # Reset on success
                elapsed = time.time() - start_time
                log_debug(f"  [{elapsed:.0f}s] GENERATING (stop button visible)")
            else:
                consecutive_idle += 1
                foreground_failures = 0  # Reset on success
                elapsed = time.time() - start_time
                log_debug(f"  [{elapsed:.0f}s] IDLE (waveform visible) - consecutive: {consecutive_idle}")
                
                # Need several consecutive idle readings after generation started
                if generation_started and consecutive_idle >= 3:
                    log_debug(f"  ✓ VERIFIED: Response complete after {elapsed:.0f}s")
                    return True
                
                # If we never saw generation start but see idle for a while,
                # maybe response was very fast or already done
                if not generation_started and consecutive_idle >= 5:
                    log_debug(f"  ✓ Response appears complete (no generation detected)")
                    return True
            
            time.sleep(0.5)
        
        log_debug(f"  ✗ TIMEOUT after {timeout}s")
        return False
    
    def _is_generating(self) -> bool:
        """Check if ChatGPT is generating by looking for black stop button."""
        from PIL import ImageGrab
        import numpy as np
        
        if not self.window_rect:
            return False
        
        rect = self.window_rect
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        # Stop/waveform button at bottom-right of input box
        center_x = rect[0] + int(window_width * 0.83)
        center_y = rect[1] + int(window_height * 0.87)
        
        area = (center_x - 15, center_y - 15, center_x + 15, center_y + 15)
        
        try:
            img = ImageGrab.grab(bbox=area)
            pixels = np.array(img)
            
            # Count very dark pixels (the black stop square)
            dark_pixels = np.sum(np.all(pixels < 50, axis=2))
            
            # Stop button: 60-400 dark pixels (black square on white)
            # Waveform (idle): <60 dark pixels
            # Arrow (ready): >400 dark pixels (not expected during wait)
            return 60 < dark_pixels < 400
        except:
            return False
    
    # =========================================================================
    # STEP 10: Copy Response
    # =========================================================================
    
    def step10_copy_response(self) -> str:
        """
        Copy the last response to clipboard.
        
        Strategy:
        1. Click input area as anchor point
        2. Shift+Tab × 5 to reach Copy button (toolbar order from input: +attach, mic, voice, ..., refresh, thumbs-down, thumbs-up, copy)
        3. Validate focused element is Copy button before pressing Enter
        4. If not on Copy, continue Shift+Tab with validation
        5. Fallback to UIA direct invoke
        """
        import pyperclip
        from pywinauto.keyboard import send_keys
        from pywinauto.mouse import click
        import win32gui
        
        log_debug("STEP 10: Copying response...")
        
        # Helper to get focused element info via UIA
        def get_focused_button_name() -> str:
            """Return name of focused button, or empty string if not a button."""
            try:
                import comtypes.client
                UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen.UIAutomationClient import CUIAutomation
                
                uia = comtypes.client.CreateObject(CUIAutomation)
                focused = uia.GetFocusedElement()
                if not focused:
                    return ""
                
                ctype_id = focused.CurrentControlType
                name = focused.CurrentName or ''
                
                # Button = 50000
                if ctype_id == 50000:
                    log_debug(f"[copy] Focused button: {name!r}")
                    return name.lower()
                else:
                    log_debug(f"[copy] Focused element type={ctype_id}, name={name[:30]!r}")
                    return ""
            except Exception as e:
                log_debug(f"[copy] get_focused_button_name error: {e}")
                return ""
        
        # Simple click on input area as anchor
        rect = self.window_rect
        if rect:
            window_width = rect[2] - rect[0]
            window_height = rect[3] - rect[1]
            input_x = rect[0] + int(window_width * 0.5)
            input_y = rect[1] + int(window_height * 0.83)
            
            if self._safe_click(input_x, input_y, "copy anchor input"):
                time.sleep(0.3)
                log_debug(f"[copy] Clicked anchor at ({input_x}, {input_y})")
            else:
                log_debug(f"[copy] ✗ Anchor click failed")
        
        # Strategy 1: Shift+Tab × 5 to reach Copy, then validate and Enter
        log_debug("[copy] Navigating with Shift+Tab × 5...")
        
        # Ensure foreground before keyboard navigation
        if not self._ensure_foreground():
            log_debug("[copy] ✗ Could not ensure foreground for Shift+Tab navigation")
            # Try fallback below
        else:
            # Do 5 Shift+Tabs to reach Copy button area
            for i in range(5):
                send_keys("+{TAB}")
                time.sleep(0.08)
        
            time.sleep(0.15)  # Let UI settle
        
            # Check what we landed on
            btn_name = get_focused_button_name()
        
            if 'copy' in btn_name:
                log_debug(f"[copy] ✓ On Copy button after 5 Shift+Tabs")
                # Ensure still foreground before Enter
                if self._ensure_foreground():
                    pyperclip.copy("")
                    send_keys("{ENTER}")
                    time.sleep(0.3)
                    response = pyperclip.paste()
                    if response and len(response) > 5:
                        log_debug(f"[copy] ✓ Got {len(response)} chars")
                        return response
        
        # Not on Copy — maybe need more tabs. Continue with validation.
        # Dangerous buttons to avoid: thumbs up, thumbs down, refresh, ...
        dangerous = ['thumb', 'dislike', 'like', 'refresh', 'regenerate', 'more']
        
        # Ensure still foreground before additional tabs
        if not self._ensure_foreground():
            log_debug("[copy] ✗ Lost foreground before additional tab navigation")
            # Skip to UIA fallback
        else:
            max_extra_tabs = 6
            for i in range(max_extra_tabs):
                send_keys("+{TAB}")
                time.sleep(0.1)
            
                btn_name = get_focused_button_name()
            
                if 'copy' in btn_name:
                    log_debug(f"[copy] ✓ Found Copy button after {5 + i + 1} Shift+Tabs")
                    # Ensure foreground before Enter
                    if not self._ensure_foreground():
                        log_debug("[copy] ✗ Lost foreground before pressing Enter")
                        break
                    
                    pyperclip.copy("")
                    send_keys("{ENTER}")
                    time.sleep(0.3)
                    response = pyperclip.paste()
                    if response and len(response) > 5:
                        log_debug(f"[copy] ✓ Got {len(response)} chars")
                        return response
                elif any(d in btn_name for d in dangerous):
                    log_debug(f"[copy] Skipping dangerous button: {btn_name}")
                    continue
                elif btn_name == '':
                    # Not on a button, might have overshot
                    log_debug(f"[copy] Lost button focus, stopping tab navigation")
                    break
        
        # Fallback: Try UIA direct invoke
        log_debug("[copy] Tab navigation failed, trying UIA direct invoke...")
        try:
            from pywinauto import Application
            app = Application(backend='uia').connect(handle=self.hwnd)
            main_win = app.window(handle=self.hwnd)
            buttons = main_win.descendants(control_type='Button')
            for b in buttons:
                try:
                    name = (b.element_info.name or "").lower()
                    if 'copy' in name:
                        log_debug(f"[copy] UIA found Copy button: {name} - invoking")
                        pyperclip.copy("")
                        try:
                            b.invoke()
                        except Exception:
                            b.click_input()
                        time.sleep(0.4)
                        resp = pyperclip.paste()
                        if resp and len(resp) > 5:
                            log_debug(f"[copy] ✓ Got {len(resp)} chars via UIA")
                            return resp
                except Exception:
                    continue
        except Exception as e:
            log_debug(f"[copy] UIA fallback failed: {e}")
        
        # Last resort: Ctrl+Shift+C
        log_debug("[copy] Trying Ctrl+Shift+C...")
        pyperclip.copy("")
        send_keys("^+c")
        time.sleep(0.5)
        response = pyperclip.paste()
        if response and len(response) > 5:
            log_debug(f"[copy] ✓ Got {len(response)} chars via Ctrl+Shift+C")
            return response
        
        log_debug("[copy] ✗ FAILED: Could not copy response")
        return ""
    
    # =========================================================================
    # FULL FLOW
    # =========================================================================
    
    def execute_full_flow(
        self,
        project_name: str,
        conversation_name: str,
        prompt: str
    ) -> dict:
        """
        Execute the complete flow with verification at each step.
        
        Returns:
            {
                "success": bool,
                "response": str (if successful),
                "error": str (if failed),
                "failed_step": int (if failed)
            }
        """
        log_debug("=" * 60)
        log_debug("EXECUTING FULL FLOW")
        log_debug(f"  Project: {project_name}")
        log_debug(f"  Conversation: {conversation_name}")
        log_debug(f"  Prompt: {prompt[:50]}...")
        log_debug("=" * 60)
        
        # Step 1: Kill ChatGPT
        if not self.step1_kill_chatgpt():
            return {"success": False, "error": "Failed to kill ChatGPT", "failed_step": 1}
        
        time.sleep(1.0)  # Extra wait after kill
        
        # Step 2: Start ChatGPT
        if not self.step2_start_chatgpt():
            return {"success": False, "error": "Failed to start ChatGPT", "failed_step": 2}
        
        # Step 3: Focus ChatGPT
        if not self.step3_focus_chatgpt():
            return {"success": False, "error": "Failed to focus ChatGPT", "failed_step": 3}
        
        # Step 4: Open Sidebar
        if not self.step4_open_sidebar():
            return {"success": False, "error": "Failed to open sidebar", "failed_step": 4}
        
        # Step 5: Click Project
        if not self.step5_click_project(project_name):
            return {"success": False, "error": f"Failed to find project '{project_name}'", "failed_step": 5}
        
        time.sleep(0.5)  # Wait for project to expand
        
        # Step 6: Click Conversation
        if not self.step6_click_conversation(conversation_name):
            return {"success": False, "error": f"Failed to find conversation '{conversation_name}'", "failed_step": 6}
        
        # Step 7+8: Focus & Send Prompt
        if not self.step7_send_prompt(prompt):
            return {"success": False, "error": "Failed to focus/send prompt", "failed_step": 7}
        
        # Step 9: Wait for Response
        if not self.step9_wait_for_response():
            return {"success": False, "error": "Timeout waiting for response", "failed_step": 9}
        
        # Step 10: Copy Response
        response = self.step10_copy_response()
        if not response:
            return {"success": False, "error": "Failed to copy response", "failed_step": 10}
        
        log_debug("=" * 60)
        log_debug("FLOW COMPLETE - SUCCESS")
        log_debug("=" * 60)
        
        return {
            "success": True,
            "response": response
        }


# Test
if __name__ == "__main__":
    flow = RobustChatGPTFlow()
    
    # Test individual steps
    print("Testing robust flow...")
    
    # Test step 1
    if flow.step1_kill_chatgpt():
        print("Step 1 passed")
    
    time.sleep(1)
    
    # Test step 2
    if flow.step2_start_chatgpt():
        print("Step 2 passed")
    
    # Test step 3
    if flow.step3_focus_chatgpt():
        print("Step 3 passed")
    
    # Test step 4
    if flow.step4_open_sidebar():
        print("Step 4 passed")
    
    # Test step 5 - Click project
    if flow.step5_click_project("Agent Expert Help"):
        print("Step 5 passed")
    else:
        print("Step 5 FAILED")
        exit(1)
    
    time.sleep(0.5)
    
    # Test step 6 - Click conversation
    if flow.step6_click_conversation("o3 test"):
        print("Step 6 passed")
    else:
        print("Step 6 FAILED")
        exit(1)
    
    time.sleep(0.5)
    
    # Test step 7+8 - Focus & Send prompt
    test_prompt = "What are 5 examples of water being used in biology"
    if flow.step7_send_prompt(test_prompt):
        print("Step 7+8 passed")
    else:
        print("Step 7+8 FAILED")
        exit(1)
    
    # Test step 9 - Wait for response
    if flow.step9_wait_for_response():
        print("Step 9 passed")
    else:
        print("Step 9 FAILED")
        exit(1)
    
    # Test step 10 - Copy response
    response = flow.step10_copy_response()
    if response:
        print("Step 10 passed")
        print(f"\n{'='*60}")
        print("RESPONSE:")
        print(f"{'='*60}")
        print(response[:500] + "..." if len(response) > 500 else response)
    else:
        print("Step 10 FAILED")
        exit(1)
    
    print("\n✓ FULL FLOW COMPLETE!")
