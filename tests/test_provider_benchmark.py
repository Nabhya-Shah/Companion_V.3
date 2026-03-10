import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provider_benchmark.py"
SPEC = importlib.util.spec_from_file_location("provider_benchmark", SCRIPT_PATH)
provider_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = provider_benchmark
SPEC.loader.exec_module(provider_benchmark)


def test_extract_text_content_handles_openai_text_parts():
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "input_text", "text": "ignored"},
        {"type": "text", "text": " world"},
    ]
    assert provider_benchmark._extract_text_content(content) == "Hello world"


def test_score_routing_case_rewards_expected_shape():
    score, notes = provider_benchmark._score_routing_case(
        {
            "parsed_json": {
                "route": "tool",
                "needs_tools": True,
                "reason": "needs exact time",
            }
        }
    )
    assert score == 30
    assert notes == []


def test_score_memory_case_checks_expected_fact_keywords():
    score, notes = provider_benchmark._score_memory_case(
        {
            "parsed_json": {
                "facts": [
                    {"category": "diet", "value": "vegetarian"},
                    {"category": "allergy", "value": "peanut allergy"},
                    {"category": "location", "value": "Berlin"},
                    {"category": "family", "value": "lives with sister"},
                ]
            }
        }
    )
    assert score == 30
    assert notes == []