#!/usr/bin/env python3
"""
Robust ChatGPT Desktop Automation Driver for Windows

This driver wraps robust_flow.py to provide a JSON-based interface
for the MCP server. All the heavy lifting is done by RobustChatGPTFlow.

Protocol:
- Receives JSON commands on stdin
- Returns JSON responses on stdout
- Debug messages go to stderr

Commands:
- check_chatgpt: Check if ChatGPT can be found/started
- focus_chatgpt: Focus the ChatGPT window
- find_conversation: Navigate to project + conversation
- send_message: Send a message
- wait_for_response: Wait for response to complete
- get_last_response: Copy and return the response
"""

import sys
import json
import os

# Add driver directory to path
_driver_dir = os.path.dirname(os.path.abspath(__file__))
if _driver_dir not in sys.path:
    sys.path.insert(0, _driver_dir)

from robust_flow import RobustChatGPTFlow, log_debug


class RobustDriver:
    """
    MCP-compatible driver using RobustChatGPTFlow.
    
    Maps MCP commands to robust_flow methods.
    """
    
    def __init__(self):
        self.flow = RobustChatGPTFlow()
        self._last_prompt = None
    
    def check_chatgpt(self) -> dict:
        """Check if ChatGPT is available (running or can be started)."""
        # Try to find existing window first
        import win32gui
        import win32process
        import psutil
        
        def find_chatgpt_window():
            result = []
            def callback(hwnd, _):
                if win32gui.IsWindow(hwnd):
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                        if proc.name().lower() == "chatgpt.exe":
                            title = win32gui.GetWindowText(hwnd)
                            if title:
                                result.append((hwnd, title))
                    except:
                        pass
                return True
            win32gui.EnumWindows(callback, None)
            return result
        
        windows = find_chatgpt_window()
        
        if windows:
            hwnd, title = windows[0]
            return {
                "success": True,
                "data": {
                    "found": True,
                    "title": title,
                    "message": "ChatGPT Desktop is running"
                }
            }
        else:
            return {
                "success": True,
                "data": {
                    "found": False,
                    "message": "ChatGPT Desktop not running (will be started automatically)"
                }
            }
    
    def focus_chatgpt(self) -> dict:
        """Focus or start ChatGPT window."""
        # Use robust flow's step sequence
        # Kill -> Start -> Focus ensures clean state
        
        if not self.flow.step1_kill_chatgpt():
            return {"success": False, "error": "Failed to kill existing ChatGPT"}
        
        if not self.flow.step2_start_chatgpt():
            return {"success": False, "error": "Failed to start ChatGPT"}
        
        if not self.flow.step3_focus_chatgpt():
            return {"success": False, "error": "Failed to focus ChatGPT"}
        
        return {"success": True}
    
    def find_conversation(self, title: str, project_name: str = None) -> dict:
        """
        Navigate to a conversation.
        
        Args:
            title: Conversation name
            project_name: Project/folder name (optional but recommended)
        """
        # Ensure we have a focused window
        if self.flow.hwnd is None:
            # Run initialization steps
            if not self.flow.step1_kill_chatgpt():
                return {"success": False, "error": "Failed to kill existing ChatGPT"}
            if not self.flow.step2_start_chatgpt():
                return {"success": False, "error": "Failed to start ChatGPT"}
            if not self.flow.step3_focus_chatgpt():
                return {"success": False, "error": "Failed to focus ChatGPT"}
        
        # Open sidebar
        if not self.flow.step4_open_sidebar():
            return {"success": False, "error": "Failed to open sidebar"}
        
        # Navigate to project (if specified)
        if project_name:
            if not self.flow.step5_click_project(project_name):
                return {"success": False, "error": f"Failed to find project: {project_name}"}
        
        # Navigate to conversation
        if not self.flow.step6_click_conversation(title):
            return {"success": False, "error": f"Failed to find conversation: {title}"}
        
        return {
            "success": True,
            "data": {
                "conversation": title,
                "project": project_name,
                "method": "robust_flow"
            }
        }
    
    def send_message(self, message: str) -> dict:
        """Send a message to the current conversation (combined focus+send)."""
        log_debug(f"[driver] send_message called, len={len(message)}")
        ok = self.flow.step7_send_prompt(message)
        log_debug(f"[driver] step7_send_prompt returned: {ok}")
        if not ok:
            return {"success": False, "error": "Failed to focus/send message"}
        self._last_prompt = message
        return {"success": True}
    
    def wait_for_response(self, timeout_ms: int = 600000) -> dict:
        """Wait for ChatGPT to finish generating."""
        timeout_sec = timeout_ms / 1000.0
        
        if not self.flow.step9_wait_for_response(timeout=timeout_sec):
            return {"success": False, "error": f"Timeout waiting for response ({timeout_ms}ms)"}
        
        return {"success": True}
    
    def get_last_response(self) -> dict:
        """Copy and return the last response."""
        response = self.flow.step10_copy_response()
        
        if not response:
            return {"success": False, "error": "Failed to copy response"}
        
        return {
            "success": True,
            "data": {
                "response": response
            }
        }
    
    # Convenience method: full escalation in one call
    def escalate(self, project_name: str, conversation: str, message: str, timeout_ms: int = 600000, run_id: str = None) -> dict:
        """
        Full escalation flow in one call using execute_full_flow.
        
        Uses robust_flow's execute_full_flow which has:
        - Proper phase logging
        - Navigation retry logic
        - Response validation
        - failed_step tracking
        
        Includes restart logic for recoverable failures (focus_failed, start_failed).
        """
        if run_id:
            log_debug(f"[{run_id}] Starting escalation: project={project_name}, conversation={conversation}")
        else:
            log_debug(f"Starting escalation: project={project_name}, conversation={conversation}")
        
        # Recoverable error reasons that warrant a full restart
        RECOVERABLE_REASONS = {"focus_failed", "start_failed", "sidebar_failed", "focus_lost"}
        max_restarts = 1
        
        for attempt in range(max_restarts + 1):
            if attempt > 0:
                log_debug(f"[{run_id or 'no-run-id'}] RESTART attempt {attempt + 1}: previous failure was recoverable")
                # Fresh flow instance to reset all state
                self.flow = RobustChatGPTFlow()
            
            # Use the full flow with all its bells and whistles
            result = self.flow.execute_full_flow(
                project_name=project_name or "",
                conversation_name=conversation,
                prompt=message
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "data": {
                        "response": result["response"],
                        "project": project_name,
                        "conversation": conversation,
                        "run_id": run_id,
                        "restart_attempts": attempt
                    }
                }
            
            # Failure - check if recoverable
            failed_step = result.get("failed_step")
            error = result.get("error", "Unknown error")
            error_reason = self._derive_error_reason(failed_step, error)
            
            log_debug(f"[{run_id or 'no-run-id'}] Escalation failed: step={failed_step}, reason={error_reason}, error={error}")
            
            # Check if we should retry
            if attempt < max_restarts and error_reason in RECOVERABLE_REASONS:
                log_debug(f"[{run_id or 'no-run-id'}] Failure is recoverable ({error_reason}), will restart...")
                import time
                time.sleep(2)  # Brief pause before restart
                continue
            
            # Not recoverable or out of retries
            return {
                "success": False,
                "error": error,
                "failed_step": failed_step,
                "error_reason": error_reason,
                "run_id": run_id,
                "restart_attempts": attempt
            }
        
        # Should never reach here, but just in case
        return {
            "success": False,
            "error": "Max restarts exceeded",
            "failed_step": None,
            "error_reason": "max_restarts",
            "run_id": run_id,
            "restart_attempts": max_restarts
        }
    
    def _derive_error_reason(self, step: int, error: str) -> str:
        """Derive a structured error reason code from step and error message."""
        if step is None:
            return "unknown"
        
        error_lower = error.lower()
        
        # Step-specific reason codes
        step_reasons = {
            1: "kill_failed",
            2: "start_failed",
            3: "focus_failed",
            4: "sidebar_failed",
            5: "project_not_found",
            6: "conversation_not_found",
            7: "send_failed",
            9: "response_timeout",
            10: "copy_failed",
        }
        
        base_reason = step_reasons.get(step, f"step{step}_failed")
        
        # Refine based on error message
        if "not found" in error_lower or "failed to find" in error_lower:
            if step == 5:
                return "project_not_found"
            elif step == 6:
                return "conversation_not_found"
        elif "timeout" in error_lower:
            return "timeout"
        elif "focus" in error_lower:
            return "focus_lost"
        elif "validation failed" in error_lower:
            return "invalid_response"
        
        return base_reason


def main():
    """Main entry point - process commands from stdin."""
    driver = RobustDriver()
    
    # Read command from stdin
    try:
        input_data = sys.stdin.read()
        command = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        return
    
    action = command.get("action")
    params = command.get("params", {})
    
    log_debug(f"Executing action: {action}")
    
    # Dispatch to appropriate handler
    if action == "check_chatgpt":
        result = driver.check_chatgpt()
    
    elif action == "focus_chatgpt":
        result = driver.focus_chatgpt()
    
    elif action == "find_conversation":
        result = driver.find_conversation(
            title=params.get("title", ""),
            project_name=params.get("project_name")
        )
    
    elif action == "send_message":
        result = driver.send_message(params.get("message", ""))
    
    elif action == "wait_for_response":
        result = driver.wait_for_response(params.get("timeout_ms", 600000))
    
    elif action == "get_last_response":
        result = driver.get_last_response()
    
    elif action == "escalate":
        # Full flow in one call
        result = driver.escalate(
            project_name=params.get("project_name"),
            conversation=params.get("conversation"),
            message=params.get("message", ""),
            timeout_ms=params.get("timeout_ms", 600000),
            run_id=params.get("run_id")
        )
    
    else:
        result = {"success": False, "error": f"Unknown action: {action}"}
    
    print(json.dumps(result))


if __name__ == "__main__":
    main()
