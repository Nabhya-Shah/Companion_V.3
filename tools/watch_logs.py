#!/usr/bin/env python3
"""
Live log viewer for Companion AI web server
Tails the log file and displays updates in real-time
"""
import os
import time
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
LOG_FILE = os.path.join(DATA_DIR, 'web_server.log')

def tail_log(filename, interval=0.5):
    """Tail a file and yield new lines as they appear"""
    with open(filename, 'r') as f:
        # Go to end of file
        f.seek(0, 2)
        
        print(f"📊 Watching {filename}")
        print("=" * 70)
        
        while True:
            line = f.readline()
            if line:
                print(line.rstrip())
                sys.stdout.flush()
            else:
                time.sleep(interval)

if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        print(f"❌ Log file not found: {LOG_FILE}")
        print("Start the web server first!")
        sys.exit(1)
    
    try:
        tail_log(LOG_FILE)
    except KeyboardInterrupt:
        print("\n👋 Log viewer stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
