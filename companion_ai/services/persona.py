"""Persona evolution service -- learns and adapts personality over time.

The persona system has three layers:
1. **Static persona** (companion.yaml) -- core personality, always present
2. **Evolved traits** (learned_traits.yaml) -- LLM-derived adaptations that grow
3. **Persona state** (in-memory singleton) -- interaction counters, rapport, history

Evolution triggers:
- PERIODIC: Every N messages, run a lightweight evolution analysis
- MEMORY_EVENT: When a high-importance fact is saved, do a micro-evolution
- SESSION_END: On shutdown, run a full evolution pass (existing behaviour)
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TRAITS_FILE = os.path.join(
    _BASE_DIR, "data", "companion_brain", "system", "learned_traits.yaml"
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EVOLVE_EVERY_N_MESSAGES = 25  # periodic trigger interval
MAX_TRAIT_HISTORY = 10  # keep last N evolution snapshots
MAX_EVOLVED_TRAITS = 12  # cap trait list to prevent prompt bloat
MAX_USER_STYLE = 8  # cap user-style observations
MAX_ONGOING_GOALS = 5  # cap goals list
MAX_RECURRING_THEMES = 5  # cap themes list

RAPPORT_LEVELS = [
    "Stranger",  # 0-10   messages
    "Acquaintance",  # 11-30  messages
    "Familiar",  # 31-80  messages
    "Comfortable",  # 81-200 messages
    "Close",  # 201+   messages
]


def _rapport_for_count(n: int) -> str:
    """Map interaction count to rapport level."""
    if n <= 10:
        return RAPPORT_LEVELS[0]
    if n <= 30:
        return RAPPORT_LEVELS[1]
    if n <= 80:
        return RAPPORT_LEVELS[2]
    if n <= 200:
        return RAPPORT_LEVELS[3]
    return RAPPORT_LEVELS[4]


# ---------------------------------------------------------------------------
# PersonaState -- in-memory singleton
# ---------------------------------------------------------------------------
@dataclass
class PersonaState:
    """Runtime persona state (loaded from / persisted to YAML)."""

    user_style: List[str] = field(default_factory=list)
    evolved_traits: List[str] = field(default_factory=list)
    rapport_level: str = "Stranger"
    interaction_count: int = 0
    last_evolved: Optional[str] = None
    trait_history: List[Dict[str, Any]] = field(default_factory=list)
    ongoing_goals: List[str] = field(default_factory=list)
    recurring_themes: List[str] = field(default_factory=list)

    # --- serialisation helpers -------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_style": self.user_style,
            "evolved_traits": self.evolved_traits,
            "rapport_level": self.rapport_level,
            "interaction_count": self.interaction_count,
            "last_evolved": self.last_evolved,
            "trait_history": self.trait_history[-MAX_TRAIT_HISTORY:],
            "ongoing_goals": self.ongoing_goals,
            "recurring_themes": self.recurring_themes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PersonaState":
        return cls(
            user_style=d.get("user_style", []) or [],
            evolved_traits=d.get("evolved_traits", []) or [],
            rapport_level=d.get("rapport_level", "Stranger"),
            interaction_count=d.get("interaction_count", 0),
            last_evolved=d.get("last_evolved"),
            trait_history=d.get("trait_history", []) or [],
            ongoing_goals=d.get("ongoing_goals", []) or [],
            recurring_themes=d.get("recurring_themes", []) or [],
        )

    # --- prompt fragment ---------------------------------------------------
    def prompt_fragment(self) -> str:
        """Return a concise block suitable for injection into the system prompt."""
        parts: List[str] = []
        if self.evolved_traits:
            parts.append(
                "[Adaptive Personality Traits]\n- " + "\n- ".join(self.evolved_traits)
            )
        if self.user_style:
            parts.append(
                "[User Communication Style]\n- " + "\n- ".join(self.user_style)
            )
        if self.ongoing_goals:
            parts.append(
                "[Ongoing Goals]\n- " + "\n- ".join(self.ongoing_goals)
            )
        if self.recurring_themes:
            parts.append(
                "[Recurring Themes]\n- " + "\n- ".join(self.recurring_themes)
            )
        if self.rapport_level:
            parts.append(f"[Rapport Level]: {self.rapport_level}")
        return "\n\n".join(parts)


_state: Optional[PersonaState] = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Load / Save helpers
# ---------------------------------------------------------------------------
def _ensure_dir():
    os.makedirs(os.path.dirname(TRAITS_FILE), exist_ok=True)


def load_traits() -> Dict[str, Any]:
    """Load raw traits dict from YAML (backwards-compat helper)."""
    _ensure_dir()
    try:
        if os.path.exists(TRAITS_FILE):
            with open(TRAITS_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load traits: {e}")
    return {}


def save_traits(data: Dict[str, Any]):
    """Save raw traits dict to YAML."""
    try:
        _ensure_dir()
        data["last_updated"] = datetime.now().isoformat()
        with open(TRAITS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        logger.info("Updated learned traits")
    except Exception as e:
        logger.error(f"Failed to save traits: {e}")


def get_state() -> PersonaState:
    """Get the singleton PersonaState (lazy-loaded from disk)."""
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                raw = load_traits()
                _state = PersonaState.from_dict(raw)
    return _state


def reset_state():
    """Reset the singleton (useful for tests)."""
    global _state
    with _lock:
        _state = None


def persist_state():
    """Write current PersonaState to disk."""
    st = get_state()
    save_traits(st.to_dict())


def ensure_traits_file():
    """Ensure the traits file exists with default content (backwards compat)."""
    if not os.path.exists(TRAITS_FILE):
        _ensure_dir()
        default = PersonaState()
        save_traits(default.to_dict())


# ---------------------------------------------------------------------------
# Trait merging -- incremental, not wholesale replacement
# ---------------------------------------------------------------------------
def _merge_list(existing: List[str], incoming: List[str], cap: int) -> List[str]:
    """Merge incoming items into existing, dedup by lowercase, cap at *cap*."""
    seen_lower = {t.lower() for t in existing}
    merged = list(existing)
    for item in incoming:
        if item.lower() not in seen_lower:
            merged.append(item)
            seen_lower.add(item.lower())
    # Keep the most recent items if over cap
    return merged[-cap:]


def _apply_evolution(new_data: Dict[str, Any]):
    """Merge LLM analysis results into the singleton PersonaState."""
    st = get_state()
    with _lock:
        # Snapshot current traits for history
        st.trait_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "evolved_traits": list(st.evolved_traits),
                "user_style": list(st.user_style),
                "ongoing_goals": list(st.ongoing_goals),
                "recurring_themes": list(st.recurring_themes),
                "rapport_level": st.rapport_level,
            }
        )

        # Incremental merge
        st.evolved_traits = _merge_list(
            st.evolved_traits,
            new_data.get("evolved_traits", []),
            MAX_EVOLVED_TRAITS,
        )
        st.user_style = _merge_list(
            st.user_style,
            new_data.get("user_style", []),
            MAX_USER_STYLE,
        )
        st.ongoing_goals = _merge_list(
            st.ongoing_goals,
            new_data.get("ongoing_goals", []),
            MAX_ONGOING_GOALS,
        )
        st.recurring_themes = _merge_list(
            st.recurring_themes,
            new_data.get("recurring_themes", []),
            MAX_RECURRING_THEMES,
        )

        # Rapport: accept LLM suggestion only if it's a known level,
        # otherwise derive from interaction count
        llm_rapport = new_data.get("rapport_level", "")
        if llm_rapport in RAPPORT_LEVELS:
            st.rapport_level = llm_rapport
        else:
            st.rapport_level = _rapport_for_count(st.interaction_count)

        st.last_evolved = datetime.now().isoformat()

    persist_state()


def _memory_backed_signals(profile_facts: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract stable goals/themes from persisted profile facts.

    This keeps persona evolution grounded in durable memory even when recent
    conversation context is sparse.
    """
    goals: List[str] = []
    themes: List[str] = []

    if not isinstance(profile_facts, dict):
        return {"ongoing_goals": goals, "recurring_themes": themes}

    goal_markers = (
        "working on",
        "building",
        "learning",
        "goal",
        "project",
        "writing",
        "restoration",
        "trying to",
    )

    for key, value in list(profile_facts.items())[:20]:
        key_text = str(key or "").replace("_", " ").strip()
        value_text = str(value or "").strip()
        merged = f"{key_text} {value_text}".lower()

        if key_text and key_text not in themes:
            themes.append(key_text)

        if any(marker in merged for marker in goal_markers):
            candidate = value_text or key_text
            if candidate and candidate not in goals:
                goals.append(candidate)

    return {
        "ongoing_goals": goals[:MAX_ONGOING_GOALS],
        "recurring_themes": themes[:MAX_RECURRING_THEMES],
    }


# ---------------------------------------------------------------------------
# Core evolution -- LLM analysis
# ---------------------------------------------------------------------------
def analyze_and_evolve(history: List[Dict[str, str]]):
    """Analyse conversation history and update traits (blocking call)."""
    if not history:
        return

    logger.info(
        "Starting persona evolution analysis (%d turns)...", len(history)
    )

    # Format history (last 20 turns)
    history_text = ""
    for turn in history[-20:]:
        user_text = (turn.get("user", "") or "")[:500]
        ai_text = (turn.get("ai", "") or "")[:500]
        history_text += f"User: {user_text}\nAI: {ai_text}\n"

    st = get_state()

    # Inject long-term profile facts to guide goals & themes
    profile_facts_str = "None recorded."
    facts = {}
    try:
        from companion_ai.memory.sqlite_backend import get_all_profile_facts
        facts = get_all_profile_facts() or {}
        if facts:
            profile_facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items())
    except Exception as e:
        logger.warning(f"Could not load profile facts for persona evolution: {e}")

    seeded = _memory_backed_signals(facts)

    prompt = f"""Analyze the following conversation between a User and an AI Companion, along with their long-term explicit profile facts.

Explicit Profile Facts:
{profile_facts_str}

Current Perception:
- User Style: {st.user_style}
- Evolved Traits: {st.evolved_traits}
- Ongoing Goals: {st.ongoing_goals}
- Recurring Themes: {st.recurring_themes}
- Memory-Backed Goal Seeds: {seeded.get('ongoing_goals', [])}
- Memory-Backed Theme Seeds: {seeded.get('recurring_themes', [])}
- Rapport: {st.rapport_level}
- Total interactions: {st.interaction_count}

Task:
1. Identify NEW observations about the user's communication style (tone, length, technicality, humor). Only list traits NOT already captured.
2. Suggest NEW personality adaptations for the AI to serve this user better. Only list traits NOT already captured.
3. Identify any NEW 'ongoing_goals' the user has expressed or seems to be working towards (e.g. 'Learn Spanish', 'Finish writing a novel').
4. Identify any NEW 'recurring_themes' or topics the user frequently brings up (e.g. 'Startups', 'Cat care', 'Existential dread').
5. Assess the current rapport level from: {RAPPORT_LEVELS}

Return ONLY a JSON object:
{{
    "user_style": ["new_trait_1", ...],
    "evolved_traits": ["new_trait_1", ...],
    "ongoing_goals": ["new_goal_1", ...],
    "recurring_themes": ["new_theme_1", ...],
    "rapport_level": "one of the levels above"
}}

If nothing new to add for a specific category, return an empty list for it. Do NOT repeat existing items.

Conversation:
{history_text}"""

    try:
        from companion_ai.llm_interface import generate_model_response

        response = generate_model_response(
            prompt,
            system_prompt=(
                "You are an expert psychologist. Output valid JSON only. "
                "No markdown."
            ),
            model="llama-3.1-8b-instant",
        )

        start = response.find("{")
        end = response.rfind("}") + 1
        if start != -1 and end > start:
            new_data = json.loads(response[start:end])
            # Always preserve deterministic memory-backed signals.
            new_data["ongoing_goals"] = list(seeded.get("ongoing_goals", [])) + list(new_data.get("ongoing_goals", []))
            new_data["recurring_themes"] = list(seeded.get("recurring_themes", [])) + list(new_data.get("recurring_themes", []))
            _apply_evolution(new_data)
            logger.info(
                "Persona evolution applied: +%d traits, +%d style",
                len(new_data.get("evolved_traits", [])),
                len(new_data.get("user_style", [])),
            )
        else:
            logger.warning(
                "Could not parse JSON from evolution response: %s",
                response[:100],
            )

    except Exception as e:
        logger.error("Persona evolution failed: %s", e)


# ---------------------------------------------------------------------------
# Trigger helpers
# ---------------------------------------------------------------------------
def trigger_evolution_background(history: List[Dict[str, str]]):
    """Run evolution analysis in a background thread."""
    thread = threading.Thread(
        target=analyze_and_evolve, args=(history,), daemon=True
    )
    thread.start()


def record_interaction():
    """Increment the interaction counter and update rapport.

    Call this once per user message.
    Returns True if a periodic evolution should be triggered.
    """
    st = get_state()
    with _lock:
        st.interaction_count += 1
        st.rapport_level = _rapport_for_count(st.interaction_count)
    return st.interaction_count % EVOLVE_EVERY_N_MESSAGES == 0


def on_memory_event(fact: str, importance: float = 0.0):
    """Called when a significant memory is saved.

    If *importance* >= 0.7, queue a micro-evolution noting the event
    (just appends a contextual trait, no LLM call for speed).
    """
    if importance < 0.7:
        return

    st = get_state()
    micro = f"Knows important detail: {fact[:60]}"
    with _lock:
        if micro.lower() not in {t.lower() for t in st.evolved_traits}:
            st.evolved_traits = _merge_list(
                st.evolved_traits, [micro], MAX_EVOLVED_TRAITS
            )
            st.last_evolved = datetime.now().isoformat()
    persist_state()
    logger.info("Micro-evolution from memory event: %s", micro[:80])
