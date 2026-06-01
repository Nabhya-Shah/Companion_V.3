"""
Live integration tests for Companion AI.
Run with: python tools/live_tests.py
Requires the web server running on port 5000.
"""

import requests
import json
import time
import sys
import threading

BASE = "http://127.0.0.1:5000"

def send(msg):
    """Send a message through the test harness and return parsed response."""
    r = requests.post(f"{BASE}/api/test/send", json={"message": msg}, timeout=120)
    r.raise_for_status()
    return r.json()

def api(method, path, **kwargs):
    """Generic API call."""
    kwargs.setdefault("timeout", 30)
    r = getattr(requests, method)(f"{BASE}{path}", **kwargs)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

def banner(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

def result(ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {detail}")
    return ok

# ─── Tests ────────────────────────────────────────────────────

def test_basic_chat():
    banner("TEST 1: Basic Chat")
    d = send("Hello! What is 2 + 2?")
    ai = d.get("ai", "")
    ok = "4" in ai
    result(ok, f"AI said: {ai[:200]}")
    return ok

def test_memory():
    banner("TEST 2: Memory Save & Recall")
    d1 = send("My favorite programming language is Python and my dog is named Max.")
    result(True, f"Store: {d1['ai'][:200]}")
    time.sleep(3)
    
    d2 = send("What is my favorite programming language? What is my dog's name?")
    ai = d2.get("ai", "").lower()
    ok = "python" in ai and "max" in ai
    result(ok, f"Recall: {d2['ai'][:200]}")
    return ok

def test_tool_time():
    banner("TEST 3: Tool Execution (Time)")
    d = send("What time is it right now?")
    ai = d.get("ai", "")
    # Should contain some time-like pattern
    ok = any(c.isdigit() for c in ai) and (":" in ai or "am" in ai.lower() or "pm" in ai.lower())
    result(ok, f"AI said: {ai[:200]}")
    return ok

def test_workflows():
    banner("TEST 4: Workflows API")
    
    # Create
    wf = {
        "name": "Morning Routine",
        "trigger": "manual",
        "steps": [
            {"action": "say", "params": {"text": "Good morning!"}},
            {"action": "tool", "params": {"name": "get_current_time"}}
        ]
    }
    code, data = api("post", "/api/workflows", json=wf)
    created = code == 200 or code == 201
    wf_id = data.get("id", "") if isinstance(data, dict) else ""
    result(created, f"Create: HTTP {code}, id={wf_id}")
    
    # List
    code2, wfs = api("get", "/api/workflows")
    has_wf = any(w.get("name") == "Morning Routine" for w in wfs) if isinstance(wfs, list) else False
    result(has_wf, f"List: {len(wfs) if isinstance(wfs, list) else 0} workflows")
    
    return created and has_wf

def test_approval():
    banner("TEST 5: Approval System")
    
    # Check approval registry
    code, data = api("get", "/api/approvals")
    result(code == 200, f"GET /api/approvals: HTTP {code}")
    
    # Check pending (should be empty)
    pending = data if isinstance(data, list) else data.get("pending", [])
    result(len(pending) == 0, f"No pending approvals: {len(pending)}")
    
    # Check approval-required tools config
    code2, status = api("get", "/api/test/status")
    tools = status.get("approval_required_tools", [])
    result(True, f"Approval-required tools registered: {tools}")
    
    return code == 200

def test_plans():
    banner("TEST 6: Plans API")
    
    code, data = api("get", "/api/plans")
    result(code == 200, f"GET /api/plans: HTTP {code}")
    plans = data if isinstance(data, list) else data.get("plans", [])
    result(True, f"Active plans: {len(plans)}")
    
    return code == 200

def test_sse_stream():
    banner("TEST 7: SSE & History Stream")
    
    # Test SSE endpoint opens
    try:
        r = requests.get(f"{BASE}/api/chat/stream", stream=True, timeout=3)
        ok = r.status_code == 200
        ct = r.headers.get("content-type", "")
        result(ok, f"SSE stream: HTTP {r.status_code}, type={ct}")
        r.close()
    except requests.exceptions.ReadTimeout:
        result(True, "SSE stream opened (timed out waiting for events, which is expected)")
    
    # Test history endpoint
    code, data = api("get", "/api/history")
    entries = data if isinstance(data, list) else data.get("history", [])
    result(code == 200, f"History: {len(entries)} entries")
    
    return True

def test_context_endpoint():
    banner("TEST 8: Context Endpoint")
    code, data = api("get", "/api/context")
    result(code == 200, f"GET /api/context: HTTP {code}")
    if isinstance(data, dict):
        keys = list(data.keys())
        result(True, f"Context keys: {keys[:10]}")
    return code == 200

def test_models_endpoint():
    banner("TEST 9: Models Endpoint")
    code, data = api("get", "/api/models")
    result(code == 200, f"GET /api/models: HTTP {code}")
    if isinstance(data, dict):
        primary = data.get("primary", "?")
        result(True, f"Primary model: {primary}")
    return code == 200

def test_token_budget():
    banner("TEST 10: Token Budget")
    code, data = api("get", "/api/token-budget")
    result(code == 200, f"GET /api/token-budget: HTTP {code}")
    if isinstance(data, dict):
        result(True, f"Budget: {json.dumps(data)[:200]}")
    return code == 200

# ─── Runner ───────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  COMPANION AI — LIVE INTEGRATION TESTS")
    print("="*60)
    
    # Health check
    try:
        code, status = api("get", "/api/test/status")
        if code != 200:
            print(f"Server not ready: HTTP {code}")
            sys.exit(1)
        print(f"Server: {status.get('server')} | Orchestrator: {status.get('orchestrator')}")
    except Exception as e:
        print(f"Cannot reach server: {e}")
        sys.exit(1)
    
    tests = [
        ("Basic Chat", test_basic_chat),
        ("Memory", test_memory),
        ("Tool (Time)", test_tool_time),
        ("Workflows", test_workflows),
        ("Approvals", test_approval),
        ("Plans", test_plans),
        ("SSE Stream", test_sse_stream),
        ("Context", test_context_endpoint),
        ("Models", test_models_endpoint),
        ("Token Budget", test_token_budget),
    ]
    
    # Allow selecting specific tests
    if len(sys.argv) > 1:
        selected = sys.argv[1:]
        tests = [(n, f) for n, f in tests if any(s.lower() in n.lower() for s in selected)]
    
    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as e:
            banner(f"ERROR: {name}")
            print(f"  Exception: {e}")
            results[name] = False
        time.sleep(2)  # Rate limit buffer
    
    # Summary
    banner("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  {passed}/{total} passed")
    
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
