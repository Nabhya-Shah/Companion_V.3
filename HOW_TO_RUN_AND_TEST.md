# How to Run and Test Companion AI

## CRITICAL: Always Use This Method

**DO NOT** run the server directly in the VS Code terminal!

### Step 1: Start Web Server in External PowerShell Window
```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\PC\Documents\GitHub\Companion_V.3'; python run_companion.py --web"
```

This opens a **separate PowerShell window** that keeps the server running.

### Step 2: Test from VS Code Terminal
```powershell
# Wait for server to start (3-4 seconds)
Start-Sleep -Seconds 4

# Then run test commands
python tools/send_debug_message.py "Your test message here"
```

## Why This Way?

1. **External window** = Server stays running independently
2. **VS Code terminal** = Free for testing and seeing output
3. **No conflicts** = Can see both server logs AND test results

## Quick Test Commands

```powershell
# Test weather tool
python tools/send_debug_message.py "What's the weather in Tokyo?"

# Test calculator
python tools/send_debug_message.py "Calculate 123 * 456"

# Test file finding
python tools/send_debug_message.py "Find PDF files in my downloads"

# Test sequential tools (agentic loop)
python tools/send_debug_message.py "Find and read the Companion AI PDF"
```

## Full Startup Pattern (Copy/Paste Ready)

```powershell
# Start server
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\PC\Documents\GitHub\Companion_V.3'; python run_companion.py --web"

# Wait and test
Start-Sleep -Seconds 4; python tools/send_debug_message.py "Test message"
```

---

**REMEMBER**: External PowerShell for server, VS Code terminal for testing!
