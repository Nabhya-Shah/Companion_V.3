#!/usr/bin/env python3
"""
View the server test log with optional filtering.

Usage:
    python tools/view_test_log.py              # Show entire log
    python tools/view_test_log.py --tail 50    # Show last 50 lines
    python tools/view_test_log.py --filter ERROR  # Show only lines with ERROR
    python tools/view_test_log.py --stats      # Show statistics
"""

import sys
from pathlib import Path
import re

ROOT_DIR = Path(__file__).parent.parent
LOG_FILE = ROOT_DIR / "data" / "test_server.log"

def show_stats(lines):
    """Show log statistics"""
    total = len(lines)
    info_count = sum(1 for line in lines if 'INFO' in line)
    warning_count = sum(1 for line in lines if 'WARNING' in line or 'WARN' in line)
    error_count = sum(1 for line in lines if 'ERROR' in line)
    tool_calls = sum(1 for line in lines if 'Function call:' in line)
    synthesized = sum(1 for line in lines if '✨ Synthesized' in line)
    
    print("=" * 70)
    print("📊 TEST LOG STATISTICS")
    print("=" * 70)
    print(f"Total lines:        {total}")
    print(f"INFO messages:      {info_count}")
    print(f"WARNINGS:           {warning_count}")
    print(f"ERRORS:             {error_count}")
    print(f"Tool calls:         {tool_calls}")
    print(f"Synthesized responses: {synthesized}")
    print("=" * 70)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="View server test log")
    parser.add_argument('--tail', type=int, help="Show last N lines")
    parser.add_argument('--filter', type=str, help="Show only lines containing this text")
    parser.add_argument('--stats', action='store_true', help="Show statistics")
    args = parser.parse_args()
    
    if not LOG_FILE.exists():
        print(f"❌ Log file not found: {LOG_FILE}")
        print("Run test_server_interactive.py first to generate logs")
        return 1
    
    # Read log file
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if args.stats:
        show_stats(lines)
        return 0
    
    # Filter lines if requested
    if args.filter:
        lines = [line for line in lines if args.filter in line]
        print(f"Showing {len(lines)} lines containing '{args.filter}':")
        print("=" * 70)
    
    # Tail if requested
    if args.tail:
        lines = lines[-args.tail:]
        print(f"Showing last {args.tail} lines:")
        print("=" * 70)
    
    # Print lines
    for line in lines:
        print(line, end='')
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
