#!/usr/bin/env python3
"""
Antagonistic test utility for Windows.

Runs alongside normal tests and randomly performs actions that can
interrupt the main tool: mouse moves/clicks, focus stealing, window
minimize/restore, occluding windows, and scrolls.

Usage:
  python src/testing/antagonist.py --duration 60 --intensity medium --target "ChatGPT"

Intensities:
  - gentle: rarer actions, fewer destructive moves
  - medium: balanced
  - aggressive: frequent actions, more focus stealing

NOTE: This intentionally interferes with your desktop session. Run only on
non-critical environments.
"""
import argparse
import random
import time
import os
import sys

# Windows-only libs
try:
    import win32api
    import win32con
    import win32gui
    import subprocess
    from pywinauto.keyboard import send_keys
    from pywinauto import Application
except Exception as e:
    print(f"[antagonist] Missing dependencies: {e}", file=sys.stderr)
    sys.exit(1)


def log(msg: str):
    print(f"[antagonist] {msg}", file=sys.stderr)


def find_hwnd_for_process_name(proc_name: str):
    try:
        import win32process
        import psutil
    except Exception:
        return None

    result = [None]

    def callback(hwnd, _):
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                import psutil
                proc = psutil.Process(pid)
                if proc.name().lower() == proc_name.lower():
                    title = win32gui.GetWindowText(hwnd)
                    if title and "IME" not in title and "Default" not in title:
                        result[0] = hwnd
                        return False
            except Exception:
                pass
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        return None
    return result[0]


def bring_to_front(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.1)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        return True
    except Exception:
        return False


def open_or_focus_notepad():
    # Try to find existing Notepad, else start one
    hwnd = find_hwnd_for_process_name("notepad.exe")
    if hwnd:
        bring_to_front(hwnd)
        return hwnd, None
    # Start new notepad
    try:
        proc = subprocess.Popen(["notepad.exe"])  # type: ignore
    except Exception:
        return None, None
    # wait a bit for window
    t0 = time.time()
    hwnd = None
    while time.time() - t0 < 5:
        hwnd = find_hwnd_for_process_name("notepad.exe")
        if hwnd:
            break
        time.sleep(0.2)
    if hwnd:
        bring_to_front(hwnd)
    return hwnd, proc


def random_mouse_move_click(screen_w, screen_h, click_chance=0.3):
    x = random.randint(0, screen_w - 1)
    y = random.randint(0, screen_h - 1)
    win32api.SetCursorPos((x, y))
    if random.random() < click_chance:
        # left click
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    log(f"mouse to ({x},{y}){' + click' if random.random() < click_chance else ''}")


def minimize_chatgpt(chatgpt_hwnd):
    try:
        win32gui.ShowWindow(chatgpt_hwnd, win32con.SW_MINIMIZE)
        log("minimized ChatGPT window")
    except Exception:
        pass


def occlude_with_notepad(opened):
    hwnd, proc = open_or_focus_notepad()
    if hwnd:
        bring_to_front(hwnd)
        log("brought Notepad to front to occlude")
        # Optionally type something to keep focus
        try:
            send_keys("This is a chaos test {ENTER}")
        except Exception:
            pass
        opened.append((hwnd, proc))


def focus_away_from_chatgpt():
    hwnd, _ = open_or_focus_notepad()
    if hwnd:
        bring_to_front(hwnd)
        log("focused away to Notepad")


def random_scroll():
    # Scroll at current mouse position
    from pywinauto.mouse import scroll
    wheel = random.choice([-3, -2, 2, 3])
    scroll(wheel_dist=wheel)
    log(f"scroll {wheel}")


def move_window(hwnd):
    """Move the target window to a random position on screen."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    try:
        screen_w = win32api.GetSystemMetrics(0)
        screen_h = win32api.GetSystemMetrics(1)
        
        # Get current window rect
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        # Random new position (keep most of window on screen)
        new_x = random.randint(-width // 2, screen_w - width // 2)
        new_y = random.randint(0, screen_h - height // 2)
        
        win32gui.MoveWindow(hwnd, new_x, new_y, width, height, True)
        log(f"moved window to ({new_x},{new_y})")
    except Exception as e:
        log(f"move_window failed: {e}")


def alt_tab_away():
    """Press Alt+Tab to switch away from current window."""
    try:
        send_keys("%{TAB}")  # Alt+Tab
        log("sent Alt+Tab")
    except Exception as e:
        log(f"alt_tab failed: {e}")


def type_garbage_in_chatgpt(chatgpt_hwnd):
    """Type random text into the ChatGPT input field (if focused)."""
    if not chatgpt_hwnd:
        return
    try:
        # First bring ChatGPT to front
        bring_to_front(chatgpt_hwnd)
        time.sleep(0.1)
        
        # Type some garbage text
        garbage = random.choice([
            "chaos test ",
            "interference ",
            "random text ",
            "123 ",
            "!!!",
            "{ENTER}",  # This could send a message!
            "test test test ",
        ])
        send_keys(garbage, pause=0.01)
        log(f"typed garbage: {repr(garbage)}")
    except Exception as e:
        log(f"type_garbage failed: {e}")


def resize_window(hwnd):
    """Resize the target window to a random size."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    try:
        screen_w = win32api.GetSystemMetrics(0)
        screen_h = win32api.GetSystemMetrics(1)
        
        # Get current window rect
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]
        
        # Random new size (reasonable bounds)
        new_width = random.randint(400, screen_w)
        new_height = random.randint(300, screen_h)
        
        win32gui.MoveWindow(hwnd, x, y, new_width, new_height, True)
        log(f"resized window to {new_width}x{new_height}")
    except Exception as e:
        log(f"resize_window failed: {e}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    p.add_argument("--intensity", choices=["gentle", "medium", "aggressive"], default="medium")
    p.add_argument("--target", default="ChatGPT", help="Target app process name without .exe or with .exe")
    p.add_argument("--seed", type=int, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    target_proc = args.target if args.target.lower().endswith(".exe") else args.target + ".exe"
    chatgpt_hwnd = find_hwnd_for_process_name(target_proc)

    # Screen size
    screen_w = win32api.GetSystemMetrics(0)
    screen_h = win32api.GetSystemMetrics(1)

    # Probability weights per intensity
    if args.intensity == "gentle":
        actions = [
            (random_mouse_move_click, 0.30),
            (focus_away_from_chatgpt, 0.15),
            (occlude_with_notepad, 0.10),
            (random_scroll, 0.15),
            (minimize_chatgpt, 0.10),
            (alt_tab_away, 0.10),
            (move_window, 0.05),
            (resize_window, 0.05),
            # No garbage typing in gentle mode
        ]
        sleep_range = (0.8, 1.6)
    elif args.intensity == "aggressive":
        actions = [
            (random_mouse_move_click, 0.20),
            (focus_away_from_chatgpt, 0.15),
            (occlude_with_notepad, 0.10),
            (random_scroll, 0.05),
            (minimize_chatgpt, 0.10),
            (alt_tab_away, 0.10),
            (move_window, 0.10),
            (resize_window, 0.05),
            (type_garbage_in_chatgpt, 0.15),  # Aggressive includes typing garbage!
        ]
        sleep_range = (0.2, 0.8)
    else:  # medium
        actions = [
            (random_mouse_move_click, 0.25),
            (focus_away_from_chatgpt, 0.15),
            (occlude_with_notepad, 0.10),
            (random_scroll, 0.10),
            (minimize_chatgpt, 0.10),
            (alt_tab_away, 0.10),
            (move_window, 0.08),
            (resize_window, 0.05),
            (type_garbage_in_chatgpt, 0.07),  # Medium has some garbage typing
        ]
        sleep_range = (0.5, 1.2)

    # Normalize weights
    total = sum(w for _, w in actions)
    actions = [(fn, w / total) for fn, w in actions]

    log(f"starting for {args.duration}s, intensity={args.intensity}")

    opened_windows = []  # track notepads we launched
    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            r = random.random()
            acc = 0.0
            chosen = None
            for fn, w in actions:
                acc += w
                if r <= acc:
                    chosen = fn
                    break
            if chosen is None:
                chosen = actions[-1][0]

            # Execute chosen action
            try:
                if chosen in (minimize_chatgpt, move_window, resize_window):
                    if chatgpt_hwnd is None:
                        chatgpt_hwnd = find_hwnd_for_process_name(target_proc)
                    if chatgpt_hwnd:
                        chosen(chatgpt_hwnd)
                elif chosen in (type_garbage_in_chatgpt,):
                    if chatgpt_hwnd is None:
                        chatgpt_hwnd = find_hwnd_for_process_name(target_proc)
                    chosen(chatgpt_hwnd)
                elif chosen in (occlude_with_notepad,):
                    chosen(opened_windows)
                elif chosen in (random_mouse_move_click,):
                    chosen(screen_w, screen_h)
                else:
                    chosen()
            except Exception:
                pass

            time.sleep(random.uniform(*sleep_range))
    except KeyboardInterrupt:
        log("interrupted by user")
    finally:
        # Optional cleanup: close any Notepads we started
        for hwnd, proc in opened_windows:
            try:
                if hwnd:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                if proc:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            except Exception:
                pass
        log("done")


if __name__ == "__main__":
    main()
