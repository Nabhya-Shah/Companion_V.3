# How to Run and Test Companion AI# How to Run and Test Companion AI



## 🎯 Quick Start## 🎯 RECOMMENDED: Interactive Testing with Log Capture (NEW!)



**Start the server in an external window:****The BEST way** - AI agent can monitor AND send test commands:



```powershell### Terminal 1: Start Interactive Server

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\PC\Documents\GitHub\Companion_V.3'; python run_companion.py --web"```powershell

```python tools/test_server_interactive.py

`a

Wait 3-4 seconds, then test with:

This will:

```powershell- ✅ Clear previous test logs

python tools/send_debug_message.py "Your test message here"- ✅ Start server with ALL output logged to `data/test_server.log`

```- ✅ Show live server output in real-time

- ✅ Allow easy stopping with Ctrl+C

**Benefits:**

- ✅ Server runs in dedicated window (always visible)### Terminal 2: Run Comprehensive Tests

- ✅ Terminal stays free for testing```powershell

- ✅ Easy to stop (close the PowerShell window)python tools/run_feature_tests.py

- ✅ Can see server logs in real-time```



---This will automatically test:

1. Token optimization (verify input tokens reduced)

## 🌐 Access Points2. Weather tool (Compound system)

3. Calculator tool

- **Main Chat Interface**: http://localhost:50004. Time tool

- **Knowledge Graph Visualization**: http://localhost:5000/graph5. Knowledge graph GRAPH_COMPLETION mode

6. Knowledge graph RELATIONSHIPS mode

---7. Knowledge graph IMPORTANT mode

8. Multi-tool workflows

## 🧪 Quick Test Commands9. Sequential tools (find → read)

10. Natural synthesis quality

```powershell

# Test weather tool (Compound system)### Review Results

python tools/send_debug_message.py "What's the weather in Tokyo?"```powershell

# View full log

# Test calculatorpython tools/view_test_log.py

python tools/send_debug_message.py "Calculate 123 * 456"

# View last 50 lines

# Test timepython tools/view_test_log.py --tail 50

python tools/send_debug_message.py "What time is it?"

# Filter for errors

# Test knowledge graph memorypython tools/view_test_log.py --filter ERROR

python tools/send_debug_message.py "What do you know about Python? Use memory_insight"

# Show statistics

# Test sequential tools (find → read)python tools/view_test_log.py --stats

python tools/send_debug_message.py "Find test_pdf.pdf and tell me what it's about"```



# Test web search**Benefits:**

python tools/send_debug_message.py "Search for latest AI news"- ✅ AI agent can see BOTH server output AND test commands

- ✅ All logs saved to file for review

# Test multi-tool workflow- ✅ Easy to stop and restart (Ctrl+C clears old logs)

python tools/send_debug_message.py "What's the weather in Paris and calculate the temperature times 2?"- ✅ Comprehensive feature testing with one command

```- ✅ Token usage visible in logs



------



## 📊 Monitoring & Tools## Alternative: VS Code Tasks



### View Knowledge GraphPress `Ctrl+Shift+P` → "Tasks: Run Task" → **"start-web-with-logs"**

```powershell

# Command line viewer - see all entities and relationshipsThis opens TWO terminal panels:

python tools/view_knowledge_graph.py- One runs the web server

- One shows live logs

# Interactive web visualization

# Visit: http://localhost:5000/graph---

```

## Manual Testing Commands

### View Logs

```powershell```powershell

# Watch logs in real-time# Test weather tool (check token usage!)

python tools/watch_logs.pypython tools/send_debug_message.py "What's the weather in Tokyo?"



# View specific log file# Test calculator

Get-Content data/web_server.log -Tail 50python tools/send_debug_message.py "Calculate 123 * 456"

```

# Test knowledge graph memory (NEW!)

### Log Filespython tools/send_debug_message.py "What do you know about Python? Use memory_insight"

- Web server: `data/web_server.log`

- Conversations: `data/logs/conv_*.jsonl`# Test relationships

- Knowledge graph: `data/knowledge_graph.pkl`python tools/send_debug_message.py "How are User and Python related? Use memory_insight with RELATIONSHIPS mode"



---# Test multi-tool workflow

python tools/send_debug_message.py "What's the weather in Paris and calculate the temperature times 2?"

## 🎨 Knowledge Graph Visualization```



Visit **http://localhost:5000/graph** for interactive visualization:## 📊 Monitoring & Debugging



**Features:**### View Live Logs

- Interactive D3.js force-directed graph```powershell

- 42+ entities color-coded by type (person, place, concept, etc.)# Watch server logs in real-time

- 40+ relationships with labeled arrowspython tools/watch_logs.py

- Search box to find entities```

- Click entities to highlight connections

- Drag nodes to rearrange### View Knowledge Graph

- Hover for detailed information (attributes, mentions, importance)```powershell

- Node size based on mentions + importance# See entities and relationships

python tools/view_knowledge_graph.py

**Color Legend:**```

- 🔴 Person

- 🔵 Place  ### Check Log Files

- 🟢 Concept- Test server log: `data/test_server.log` (cleared each test run)

- 🟠 Thing- Web server logs: `data/web_server.log` (persistent)

- 🟣 Organization- Conversation logs: `data/logs/conv_*.jsonl`

- 🌸 Event

- 🔷 Weather/Temperature---

- 📄 Documents

**REMEMBER**: Use `test_server_interactive.py` for best testing experience! 🎉

---

## ✅ Verified Features

All tested and working:
1. ✅ Weather (Groq Compound system)
2. ✅ Calculator
3. ✅ Time
4. ✅ Sequential tools (find → read)
5. ✅ Web search
6. ✅ Knowledge graph (GRAPH_COMPLETION, RELATIONSHIPS, IMPORTANT modes)
7. ✅ Multi-tool workflows
8. ✅ Natural synthesis (1-2 sentence responses)
9. ✅ Token optimization (60-70% reduction confirmed via Groq dashboard)
10. ✅ Interactive graph visualization

---

**REMEMBER**: Always start server in external window first! 🚀
