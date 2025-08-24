"""Unified launcher for Companion AI.

Usage examples (PowerShell):
  python run_companion.py                 # Start interactive chat (default)
  python run_companion.py --chat          # Same as above
  python run_companion.py --memstats      # Print memory stats then exit
  python run_companion.py --profile       # Dump stored profile facts
  python run_companion.py --cleanup       # Run smart memory cleanup
  python run_companion.py --reset-memory  # Wipe ALL memory (danger)

Environment expected (.env):
  GROQ_API_KEY=...
  (optional) GROQ_MEMORY_API_KEY=...

This script wraps existing modules so you have a single entrypoint.
"""
from __future__ import annotations
import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Ensure project root on sys.path for direct module imports even if launched elsewhere
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from companion_ai import memory as mem  # noqa

def _load_chat_cli():
    """Attempt to load chat_cli module robustly.
    Returns module object or raises the last ImportError.
    """
    # Try direct import first
    try:
        import chat_cli  # type: ignore
        return chat_cli
    except Exception as e1:  # pragma: no cover (rare path)
        # Attempt relative path execution fallback
        candidate = os.path.join(PROJECT_ROOT, 'chat_cli.py')
        if os.path.isfile(candidate):
            import importlib.util
            spec = importlib.util.spec_from_file_location('chat_cli_fallback', candidate)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)  # type: ignore
                    return module
                except Exception as e2:  # pragma: no cover
                    raise ImportError(f"Failed to import chat_cli (direct: {e1}); fallback: {e2}")
        raise ImportError(f"Failed to import chat_cli: {e1}")

chat_cli = _load_chat_cli()


def ensure_env():
    if not os.getenv("GROQ_API_KEY"):
        print("[WARN] GROQ_API_KEY not set – chat responses will be offline placeholders.")

def cmd_memstats():
    stats = mem.get_memory_stats()
    print("Memory Stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def cmd_profile():
    facts = mem.get_all_profile_facts()
    if not facts:
        print("No profile facts stored yet.")
        return
    print("Profile Facts:")
    for k, v in facts.items():
        print(f"  {k}: {v}")


def cmd_cleanup():
    mem.smart_memory_cleanup()


def cmd_reset():
    confirm = input("Type 'YES' to confirm full memory wipe: ").strip()
    if confirm == 'YES':
        mem.clear_all_memory()
    else:
        print("Aborted.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Companion AI unified launcher")
    g = p.add_mutually_exclusive_group()
    g.add_argument('--chat', action='store_true', help='Start interactive chat (default)')
    g.add_argument('--memstats', action='store_true', help='Show memory statistics and exit')
    g.add_argument('--profile', action='store_true', help='Show stored profile facts and exit')
    g.add_argument('--cleanup', action='store_true', help='Run smart memory cleanup and exit')
    g.add_argument('--reset-memory', action='store_true', help='WIPE all memory tables (danger)')
    p.add_argument('--debug', action='store_true', help='Print debug environment info then continue')
    return p.parse_args(argv)


def main(argv: list[str] | None = None):
    ns = parse_args(argv or sys.argv[1:])
    ensure_env()

    if getattr(ns, 'debug', False):
        print('[DEBUG] Python:', sys.version)
        print('[DEBUG] CWD:', os.getcwd())
        print('[DEBUG] PROJECT_ROOT:', PROJECT_ROOT)
        print('[DEBUG] sys.path[0:3]:', sys.path[:3])
        print('[DEBUG] GROQ_API_KEY set:', bool(os.getenv('GROQ_API_KEY')))
        print('[DEBUG] chat_cli module:', chat_cli.__file__ if hasattr(chat_cli, '__file__') else 'in-memory')

    if ns.memstats:
        cmd_memstats(); return
    if ns.profile:
        cmd_profile(); return
    if ns.cleanup:
        cmd_cleanup(); return
    if ns.reset_memory:
        cmd_reset(); return
    # default / chat path
    chat_cli.main()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
