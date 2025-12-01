#!/usr/bin/osascript
(*
ChatGPT Desktop Automation Driver for macOS

Uses AppleScript to automate the ChatGPT Desktop application.
Receives commands as arguments, returns JSON to stdout.

Usage:
    osascript driver.scpt '{"action": "check_chatgpt"}'
*)

on run argv
    set inputJSON to item 1 of argv
    
    try
        -- Parse the JSON input (basic parsing)
        set command to parseJSON(inputJSON)
        set actionName to getJSONValue(command, "action")
        
        -- Dispatch to appropriate handler
        if actionName is "check_chatgpt" then
            return checkChatGPT()
        else if actionName is "focus_chatgpt" then
            return focusChatGPT()
        else if actionName is "find_conversation" then
            set convTitle to getJSONValue(command, "params.title")
            return findConversation(convTitle)
        else if actionName is "send_message" then
            set msgText to getJSONValue(command, "params.message")
            return sendMessage(msgText)
        else if actionName is "wait_for_response" then
            set timeoutMs to getJSONValue(command, "params.timeout_ms")
            return waitForResponse(timeoutMs)
        else if actionName is "get_last_response" then
            return getLastResponse()
        else
            return "{\"success\": false, \"error\": \"Unknown action: " & actionName & "\"}"
        end if
        
    on error errMsg
        return "{\"success\": false, \"error\": \"" & escapeJSON(errMsg) & "\"}"
    end try
end run

-- Check if ChatGPT is running
on checkChatGPT()
    tell application "System Events"
        set isRunning to exists (processes where name is "ChatGPT")
    end tell
    
    if isRunning then
        return "{\"success\": true, \"data\": {\"found\": true}}"
    else
        return "{\"success\": true, \"data\": {\"found\": false, \"message\": \"ChatGPT Desktop not running\"}}"
    end if
end checkChatGPT

-- Bring ChatGPT to foreground
on focusChatGPT()
    try
        tell application "ChatGPT" to activate
        delay 0.5
        return "{\"success\": true}"
    on error errMsg
        return "{\"success\": false, \"error\": \"" & escapeJSON(errMsg) & "\"}"
    end try
end focusChatGPT

-- Find and select a conversation by title
on findConversation(convTitle)
    try
        tell application "ChatGPT" to activate
        delay 0.3
        
        -- Use Cmd+K to open search
        tell application "System Events"
            keystroke "k" using command down
        end tell
        delay 0.5
        
        -- Type the conversation title
        tell application "System Events"
            keystroke "a" using command down
            delay 0.1
            keystroke convTitle
        end tell
        delay 0.5
        
        -- Select first result and open
        tell application "System Events"
            key code 125 -- Down arrow
            delay 0.2
            key code 36 -- Enter
        end tell
        delay 0.5
        
        return "{\"success\": true, \"data\": {\"conversation\": \"" & escapeJSON(convTitle) & "\"}}"
        
    on error errMsg
        return "{\"success\": false, \"error\": \"" & escapeJSON(errMsg) & "\"}"
    end try
end findConversation

-- Send a message
on sendMessage(msgText)
    try
        tell application "ChatGPT" to activate
        delay 0.3
        
        -- Set clipboard and paste
        set the clipboard to msgText
        delay 0.1
        
        tell application "System Events"
            keystroke "v" using command down
        end tell
        delay 0.3
        
        -- Press Enter to send
        tell application "System Events"
            key code 36 -- Enter
        end tell
        delay 0.3
        
        return "{\"success\": true}"
        
    on error errMsg
        return "{\"success\": false, \"error\": \"" & escapeJSON(errMsg) & "\"}"
    end try
end sendMessage

-- Wait for response to complete
on waitForResponse(timeoutMs)
    set timeoutSec to timeoutMs / 1000
    set startTime to current date
    
    -- Initial delay
    delay 2
    
    -- Simple wait strategy - wait for stabilization
    repeat
        set elapsed to (current date) - startTime
        if elapsed > timeoutSec then
            return "{\"success\": false, \"error\": \"Timeout waiting for response\"}"
        end if
        
        -- Wait and check
        delay 2
        
        if elapsed > 5 then
            delay 3
            return "{\"success\": true, \"data\": {\"waited_ms\": " & (elapsed * 1000) & "}}"
        end if
    end repeat
end waitForResponse

-- Get the last response
on getLastResponse()
    try
        tell application "ChatGPT" to activate
        delay 0.3
        
        -- Try to copy last response
        -- Clear clipboard first
        set the clipboard to ""
        
        -- Try Cmd+Shift+C for copy last message
        tell application "System Events"
            keystroke "c" using {command down, shift down}
        end tell
        delay 0.3
        
        set responseText to the clipboard
        
        if responseText is "" then
            -- Fallback: select all and copy
            tell application "System Events"
                keystroke "a" using command down
                delay 0.2
                keystroke "c" using command down
            end tell
            delay 0.2
            set responseText to the clipboard
        end if
        
        if responseText is not "" then
            return "{\"success\": true, \"data\": {\"response\": \"" & escapeJSON(responseText) & "\"}}"
        else
            return "{\"success\": false, \"error\": \"Could not copy response\"}"
        end if
        
    on error errMsg
        return "{\"success\": false, \"error\": \"" & escapeJSON(errMsg) & "\"}"
    end try
end getLastResponse

-- Helper: Escape string for JSON
on escapeJSON(str)
    set escapedStr to ""
    repeat with char in str
        if char is "\"" then
            set escapedStr to escapedStr & "\\\""
        else if char is "\\" then
            set escapedStr to escapedStr & "\\\\"
        else if char is return then
            set escapedStr to escapedStr & "\\n"
        else if char is linefeed then
            set escapedStr to escapedStr & "\\n"
        else if char is tab then
            set escapedStr to escapedStr & "\\t"
        else
            set escapedStr to escapedStr & char
        end if
    end repeat
    return escapedStr
end escapeJSON

-- Helper: Basic JSON parsing (simplified)
on parseJSON(jsonStr)
    return jsonStr
end parseJSON

-- Helper: Get value from JSON path (simplified)
on getJSONValue(jsonStr, keyPath)
    -- This is a very simplified JSON parser
    -- For production, consider using a proper JSON library
    
    set AppleScript's text item delimiters to "\""
    set parts to text items of jsonStr
    
    set keyParts to my splitString(keyPath, ".")
    set targetKey to item 1 of keyParts
    
    repeat with i from 1 to count of parts
        if item i of parts is targetKey then
            -- Next non-delimiter item should be the value
            if (i + 2) ≤ (count of parts) then
                return item (i + 2) of parts
            end if
        end if
    end repeat
    
    return ""
end getJSONValue

-- Helper: Split string
on splitString(theString, theDelimiter)
    set AppleScript's text item delimiters to theDelimiter
    set theItems to text items of theString
    set AppleScript's text item delimiters to ""
    return theItems
end splitString
