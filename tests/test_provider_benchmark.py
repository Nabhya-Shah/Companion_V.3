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


def test_score_memory_schema_case_rewards_structured_facts():
    result = {
        "parsed_json": {
            "facts": [
                {
                    "key": "favorite_snack",
                    "value": "pistachios",
                    "confidence": 0.93,
                    "evidence": "my favorite snack is pistachios",
                },
                {
                    "key": "sleep_pattern",
                    "value": "night owl",
                    "confidence": 0.88,
                    "evidence": "I'm a night owl",
                },
                {
                    "key": "work_focus",
                    "value": "TypeScript",
                    "confidence": 0.8,
                    "evidence": "my work lately has been in TypeScript",
                },
            ]
        }
    }

    score, notes = provider_benchmark._score_memory_schema_case(result)

    assert score >= 24
    assert notes == []


def test_score_memory_conflict_case_prefers_latest_fact():
    result = {
        "parsed_json": {
            "facts": [
                {"key": "city", "value": "Chicago"},
                {"key": "pets", "value": "two cats"},
            ]
        }
    }

    score, notes = provider_benchmark._score_memory_conflict_case(result)

    assert score >= 25
    assert notes == []


def test_score_memory_precision_case_penalizes_unsupported_inference():
    result = {
        "parsed_json": {
            "facts": [
                {"key": "drink_preference", "value": "pour-over coffee"},
                {"key": "mood", "value": "anxious"},
            ]
        }
    }

    score, notes = provider_benchmark._score_memory_precision_case(result)

    assert score < 30
    assert any("unsupported inferred traits" in note for note in notes)


def test_build_cases_includes_memory_evaluation_cases():
    case_ids = [case["id"] for case in provider_benchmark._build_cases()]

    assert "memory_fact_extraction" in case_ids
    assert "memory_structured_schema" in case_ids
    assert "memory_conflict_resolution" in case_ids
    assert "memory_precision_no_inference" in case_ids