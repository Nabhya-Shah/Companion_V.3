"""Computer-use runtime helpers for high-risk desktop/browser control.

This module intentionally keeps execution deterministic:
- Browser-aware actions route through existing Playwright browser agent when possible.
- Linux desktop actions use xdotool when available.
- All methods return explicit text outcomes and avoid raising on normal runtime misses.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import time


logger = logging.getLogger(__name__)


class ComputerAgent:
    """Best-effort computer control runtime used by tool_use_computer."""

    def __init__(self) -> None:
        self._last_action_ts: float | None = None

    def mark_action(self) -> None:
        self._last_action_ts = time.time()

    def click_element(self, text: str) -> str:
        target = str(text or "").strip()
        if not target:
            return "click failed: missing target text"

        # Primary path: use browser text click for deterministic DOM interaction.
        try:
            from companion_ai.agents.browser import sync_click

            result = sync_click("", target)
            if isinstance(result, str) and not result.lower().startswith("error"):
                return result
        except Exception as e:
            logger.debug("Browser click path unavailable: %s", e)

        # Secondary path: coordinate click support via xdotool.
        # Format accepted: "x,y" (e.g. "640,360")
        if "," in target:
            pieces = [p.strip() for p in target.split(",", 1)]
            if len(pieces) == 2 and pieces[0].isdigit() and pieces[1].isdigit():
                x, y = pieces
                ok, err = self._run_xdotool(["mousemove", x, y, "click", "1"])
                if ok:
                    return f"clicked:{x},{y}"
                return f"click failed: {err}"

        return (
            "click failed: runtime could not resolve a desktop element by text. "
            "Use browser context text or coordinates 'x,y'."
        )

    def type_text(self, text: str, enter: bool = True) -> str:
        content = str(text or "")
        if not content:
            return "type failed: missing text"

        ok, err = self._run_xdotool(["type", "--delay", "1", content])
        if not ok:
            return f"type failed: {err}"

        if enter:
            ok_enter, err_enter = self._run_xdotool(["key", "Return"])
            if not ok_enter:
                return f"type failed: {err_enter}"

        return f"typed:{content}:{enter}"

    def press_key(self, key: str) -> str:
        normalized = self._normalize_key(key)

        ok, _ = self._run_xdotool(["key", normalized])
        if ok:
            return f"pressed:{key}"

        # Browser fallback when desktop key injection is unavailable.
        try:
            from companion_ai.agents.browser import sync_press_key

            result = sync_press_key(self._to_playwright_key(key))
            if isinstance(result, str) and not result.lower().startswith("error"):
                return f"pressed:{key}"
            return f"press failed: {result}"
        except Exception as e:
            return f"press failed: {e}"

    def launch_app(self, name: str) -> str:
        target = str(name or "").strip()
        if not target:
            return "launch failed: missing app or target"

        if self._looks_like_url(target):
            try:
                from companion_ai.agents.browser import sync_goto

                result = sync_goto(target)
                if isinstance(result, str) and not result.lower().startswith("error"):
                    return f"launched:{target}"
                return f"launch failed: {result}"
            except Exception as e:
                return f"launch failed: {e}"

        argv = self._safe_split_command(target)
        if not argv:
            return "launch failed: invalid command"

        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"launched:{target}"
        except Exception:
            # Linux fallback for desktop apps/files/URLs.
            if shutil.which("xdg-open"):
                try:
                    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"launched:{target}"
                except Exception as e:
                    return f"launch failed: {e}"
            return "launch failed: command not found and xdg-open unavailable"

    def scroll(self, direction: str) -> str:
        direction_norm = str(direction or "").strip().lower()
        if direction_norm not in {"up", "down"}:
            return f"scroll failed: unknown direction {direction}"

        button = "4" if direction_norm == "up" else "5"
        ok, _ = self._run_xdotool(["click", button])
        if ok:
            return f"scrolled:{direction_norm}"

        fallback_key = "PageUp" if direction_norm == "up" else "PageDown"
        press_result = self.press_key(fallback_key)
        if press_result.startswith("pressed:"):
            return f"scrolled:{direction_norm}"
        return f"scroll failed: {press_result}"

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        candidate = value.strip().lower()
        if not candidate:
            return False

        if candidate.startswith("http://") or candidate.startswith("https://"):
            return True

        if " " in candidate or "/" in candidate or "\\" in candidate:
            return False

        # Guard against common executable/script names that include dots.
        if candidate.endswith((".exe", ".app", ".desktop", ".sh", ".py", ".bat", ".cmd")):
            return False

        if candidate.startswith("www."):
            return True

        # Heuristic for domain-like values: host.tld with alpha TLD.
        return bool(re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", candidate))

    @staticmethod
    def _safe_split_command(command: str) -> list[str]:
        try:
            argv = shlex.split(command)
        except Exception:
            return []
        return [part for part in argv if part]

    @staticmethod
    def _normalize_key(key: str) -> str:
        token = str(key or "Enter").strip()
        if not token:
            return "Return"

        lower = token.lower()
        aliases = {
            "enter": "Return",
            "return": "Return",
            "esc": "Escape",
            "escape": "Escape",
            "del": "Delete",
            "pgup": "Page_Up",
            "pageup": "Page_Up",
            "pgdn": "Page_Down",
            "pagedown": "Page_Down",
            "win": "Super_L",
            "windows": "Super_L",
            "cmd": "Super_L",
        }
        return aliases.get(lower, token)

    @staticmethod
    def _to_playwright_key(key: str) -> str:
        token = str(key or "Enter").strip()
        lower = token.lower()
        mapping = {
            "return": "Enter",
            "enter": "Enter",
            "esc": "Escape",
            "escape": "Escape",
            "pgup": "PageUp",
            "pageup": "PageUp",
            "pgdn": "PageDown",
            "pagedown": "PageDown",
            "win": "Meta",
            "windows": "Meta",
            "cmd": "Meta",
        }
        return mapping.get(lower, token)

    def _run_xdotool(self, args: list[str]) -> tuple[bool, str]:
        if not shutil.which("xdotool"):
            return False, "xdotool_not_installed"
        if not os.getenv("DISPLAY"):
            return False, "display_not_available"

        cmd = ["xdotool", *args]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
            if proc.returncode == 0:
                return True, ""
            err = (proc.stderr or proc.stdout or f"exit_code:{proc.returncode}").strip()
            return False, err
        except Exception as e:
            return False, str(e)


computer_agent = ComputerAgent()
