"""Local model doctor/bootstrap utility for Companion V3.

Run:
    ./.venv/bin/python scripts/local_model_doctor.py
    ./.venv/bin/python scripts/local_model_doctor.py --bootstrap
    ./.venv/bin/python scripts/local_model_doctor.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from companion_ai.core import config as core_config
from companion_ai.local_llm import VLLMBackend, OllamaBackend


def _looks_like_ollama_model(name: str) -> bool:
    token = str(name or "").strip()
    if not token:
        return False
    # HuggingFace/vLLM identifiers usually contain '/'.
    return "/" not in token


def _ollama_model_present(installed_models: list[str], wanted_model: str) -> bool:
    """Return True when wanted_model exists, allowing tag normalization.

    Example: wanted "nomic-embed-text" should match installed
    "nomic-embed-text:latest".
    """
    wanted = str(wanted_model or "").strip().lower()
    if not wanted:
        return False

    candidates = {str(m or "").strip().lower() for m in installed_models}
    if wanted in candidates:
        return True

    wanted_base = wanted.split(":", 1)[0]
    for installed in candidates:
        if installed == wanted_base:
            return True
        if installed.split(":", 1)[0] == wanted_base:
            return True
    return False


def _build_report(bootstrap: bool = False) -> dict[str, Any]:
    cfg = core_config.get_local_model_runtime_config()
    runtime = cfg.get("runtime", "hybrid")

    vllm = VLLMBackend()
    ollama = OllamaBackend()

    vllm_available = bool(vllm.is_available())
    ollama_available = bool(ollama.is_available())

    vllm_models = vllm.list_models() if vllm_available else []
    ollama_models = ollama.list_models() if ollama_available else []

    if runtime == "vllm":
        selected_available = vllm_available
    elif runtime == "ollama":
        selected_available = ollama_available
    else:
        selected_available = vllm_available or ollama_available

    preferred = cfg.get("preferred_models", {})
    recommended_commands: list[str] = []
    bootstrap_actions: list[dict[str, Any]] = []

    if not vllm_available:
        recommended_commands.append(
            "python -m vllm.entrypoints.openai.api_server --model "
            f"{core_config.LOCAL_HEAVY_MODEL} --host 0.0.0.0 --port 8000"
        )
    if not ollama_available:
        recommended_commands.append("ollama serve")

    missing_ollama_models: list[str] = []
    if ollama_available:
        wanted = [
            preferred.get("embedding"),
            preferred.get("memory_local"),
            core_config.LOCAL_VISION_MODEL,
        ]
        seen = set()
        for model in wanted:
            model_name = str(model or "").strip()
            if not _looks_like_ollama_model(model_name):
                continue
            if model_name in seen:
                continue
            seen.add(model_name)
            if not _ollama_model_present(ollama_models, model_name):
                missing_ollama_models.append(model_name)

    if ollama_available and missing_ollama_models:
        for model in missing_ollama_models:
            recommended_commands.append(f"ollama pull {model}")

    if bootstrap and ollama_available and missing_ollama_models:
        has_ollama_bin = shutil.which("ollama") is not None
        if has_ollama_bin:
            for model in missing_ollama_models:
                cmd = ["ollama", "pull", model]
                try:
                    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
                    bootstrap_actions.append(
                        {
                            "command": " ".join(cmd),
                            "ok": proc.returncode == 0,
                            "returncode": proc.returncode,
                            "stdout_tail": (proc.stdout or "")[-300:],
                            "stderr_tail": (proc.stderr or "")[-300:],
                        }
                    )
                except Exception as exc:
                    bootstrap_actions.append(
                        {
                            "command": " ".join(cmd),
                            "ok": False,
                            "error": str(exc),
                        }
                    )
        else:
            bootstrap_actions.append(
                {
                    "command": "ollama pull <model>",
                    "ok": False,
                    "error": "ollama binary not found in PATH",
                }
            )

    ok = bool(selected_available or cfg.get("allow_cloud_fallback", True))
    status = "ok" if ok else "degraded"

    return {
        "status": status,
        "runtime": runtime,
        "profile": cfg.get("profile"),
        "chat_provider": cfg.get("chat_provider"),
        "allow_cloud_fallback": bool(cfg.get("allow_cloud_fallback", True)),
        "min_vram_gb": cfg.get("min_vram_gb"),
        "vllm": {
            "available": vllm_available,
            "models": vllm_models,
        },
        "ollama": {
            "available": ollama_available,
            "models": ollama_models,
            "missing_models": missing_ollama_models,
        },
        "selected_runtime_available": selected_available,
        "recommended_commands": recommended_commands,
        "bootstrap_actions": bootstrap_actions,
        "effective_models": preferred,
        "computer_use_defaults": cfg.get("computer_use_defaults", {}),
    }


def _print_human_report(report: dict[str, Any]) -> None:
    print("=== Companion Local Model Doctor ===")
    print(f"Status: {report.get('status')}")
    print(f"Runtime/Profile: {report.get('runtime')} / {report.get('profile')}")
    print(f"Cloud fallback allowed: {report.get('allow_cloud_fallback')}")
    print()

    vllm = report.get("vllm", {})
    print(f"vLLM available: {vllm.get('available')}")
    if vllm.get("models"):
        print("vLLM models:")
        for model in vllm["models"]:
            print(f"  - {model}")

    ollama = report.get("ollama", {})
    print(f"Ollama available: {ollama.get('available')}")
    if ollama.get("models"):
        print("Ollama models:")
        for model in ollama["models"][:10]:
            print(f"  - {model}")

    missing = ollama.get("missing_models") or []
    if missing:
        print("Missing Ollama models:")
        for model in missing:
            print(f"  - {model}")

    commands = report.get("recommended_commands") or []
    if commands:
        print()
        print("Recommended commands:")
        for cmd in commands:
            print(f"  {cmd}")

    actions = report.get("bootstrap_actions") or []
    if actions:
        print()
        print("Bootstrap actions:")
        for action in actions:
            cmd = action.get("command")
            ok = action.get("ok")
            print(f"  - {cmd}: {'OK' if ok else 'FAILED'}")
            if action.get("error"):
                print(f"    error: {action['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Companion local model doctor/bootstrap")
    parser.add_argument("--bootstrap", action="store_true", help="Attempt safe bootstrap actions (e.g., ollama pull for missing models)")
    parser.add_argument("--json", action="store_true", help="Output JSON report only")
    args = parser.parse_args()

    report = _build_report(bootstrap=args.bootstrap)

    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        _print_human_report(report)

    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
