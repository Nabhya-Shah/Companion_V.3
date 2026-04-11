from companion_ai.llm.groq_provider import _backfill_use_computer_args, _infer_use_computer_args


def test_infer_use_computer_args_prefers_first_numbered_step():
    prompt = (
        "Use computer control and execute this exact sequence now:\n"
        "1) Launch gnome-terminal\n"
        "2) Type: echo COMPANION_UI_TEST_ONE\n"
        "3) Press Enter\n"
    )

    inferred = _infer_use_computer_args(prompt)

    assert inferred["action"] == "launch"
    assert inferred["text"] == "gnome-terminal"


def test_infer_use_computer_args_type_exact_text_phrase():
    inferred = _infer_use_computer_args(
        "Use computer control now: type exactly this text: echo COMPANION_UI_TEST_ONE"
    )

    assert inferred["action"] == "type"
    assert inferred["text"] == "echo COMPANION_UI_TEST_ONE"


def test_backfill_use_computer_args_from_request_when_action_missing():
    backfilled = _backfill_use_computer_args(
        {},
        "Use computer control now: press Ctrl+Shift+T once to open another terminal tab.",
        requires_computer=True,
    )

    assert backfilled["action"] == "press"
    assert backfilled["text"] == "ctrl+shift+t"


def test_backfill_use_computer_args_fallback_press_enter_when_unparsable():
    backfilled = _backfill_use_computer_args({}, "Use computer control now.", requires_computer=True)

    assert backfilled["action"] == "press"
    assert backfilled["text"] == "Enter"
