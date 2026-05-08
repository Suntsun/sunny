from sunny.core.models.plan import PlanV2, Step
from sunny.core.orchestrator.validator import validate_plan


def _step(step_id="s1", plugin="files", action="read_file", params=None, depends_on=None):
    if params is None:
        params = {"path": "x"} if action == "read_file" else {}
    return Step(
        step_id=step_id,
        plugin=plugin,
        action=action,
        params=params,
        depends_on=depends_on or [],
    )


def _plan(intent="files", steps=None, requires_confirmation=False, needs_clarification=False, confidence=0.9):
    if steps is None and intent != "conversation":
        steps = [_step()]
    return PlanV2(
        intent=intent,
        confidence=confidence,
        needs_clarification=needs_clarification,
        requires_confirmation=requires_confirmation,
        steps=steps if steps is not None else [],
    )


def test_validate_conversation_plan_is_valid():
    p = _plan(intent="conversation", steps=[])
    r = validate_plan(p)
    assert r.valid
    assert r.errors == []
    assert not r.effective_requires_confirmation


def test_validate_simple_files_plan_is_valid():
    r = validate_plan(_plan())
    assert r.valid
    assert not r.errors
    assert not r.effective_requires_confirmation


def test_validate_unknown_plugin_fails():
    p = _plan(steps=[_step(plugin="foo")])
    r = validate_plan(p)
    assert not r.valid
    assert "plugin desconocido" in r.errors[0]


def test_validate_unknown_action_fails():
    p = _plan(steps=[_step(action="bad")])
    r = validate_plan(p)
    assert not r.valid
    assert "no existe" in r.errors[0]


def test_validate_collects_multiple_errors():
    p = _plan(steps=[_step(step_id="s1", plugin="x"), _step(step_id="s2", action="y")])
    r = validate_plan(p)
    assert len(r.errors) == 2


def test_effective_confirmation_for_delete():
    r = validate_plan(_plan(steps=[_step(action="delete")]))
    assert r.effective_requires_confirmation


def test_effective_confirmation_for_write_file():
    assert validate_plan(_plan(steps=[_step(action="write_file")])).effective_requires_confirmation


def test_effective_confirmation_for_move():
    assert validate_plan(_plan(steps=[_step(action="move")])).effective_requires_confirmation


def test_effective_confirmation_for_copy():
    assert validate_plan(_plan(steps=[_step(action="copy")])).effective_requires_confirmation


def test_effective_confirmation_for_empty_recycle_bin():
    assert validate_plan(_plan(steps=[_step(action="empty_recycle_bin")])).effective_requires_confirmation


def test_effective_confirmation_for_kill_process():
    assert validate_plan(_plan(steps=[_step(plugin="os_control", action="kill_process")])).effective_requires_confirmation


def test_effective_confirmation_for_shutdown():
    assert validate_plan(_plan(steps=[_step(plugin="os_control", action="shutdown")])).effective_requires_confirmation


def test_effective_confirmation_for_restart():
    assert validate_plan(_plan(steps=[_step(plugin="os_control", action="restart")])).effective_requires_confirmation


def test_no_confirmation_for_read_file():
    assert not validate_plan(_plan()).effective_requires_confirmation


def test_no_confirmation_for_open_app():
    assert not validate_plan(_plan(steps=[_step(plugin="os_control", action="open_app")])).effective_requires_confirmation


def test_no_confirmation_for_screenshot():
    assert not validate_plan(_plan(steps=[_step(plugin="vision", action="screenshot")])).effective_requires_confirmation


def test_no_confirmation_for_click():
    assert not validate_plan(_plan(steps=[_step(plugin="gui", action="click")])).effective_requires_confirmation


def test_no_confirmation_for_ask_external():
    assert not validate_plan(_plan(steps=[_step(plugin="ai_bridge", action="ask_external")])).effective_requires_confirmation


def test_bulk_threshold_triggers_confirmation():
    steps = [_step(step_id=f"s{i}") for i in range(6)]
    assert validate_plan(_plan(steps=steps)).effective_requires_confirmation


def test_below_bulk_threshold_no_extra_confirmation():
    steps = [_step(step_id=f"s{i}") for i in range(5)]
    assert not validate_plan(_plan(steps=steps)).effective_requires_confirmation


def test_warning_when_llm_underestimates_confirmation():
    p = _plan(steps=[_step(action="delete")], requires_confirmation=False)
    r = validate_plan(p)
    assert r.warnings
    assert r.effective_requires_confirmation


def test_no_warning_when_llm_correctly_marks_confirmation():
    p = _plan(steps=[_step(action="delete")], requires_confirmation=True)
    r = validate_plan(p)
    assert not r.warnings


def test_no_warning_for_non_destructive_plan():
    r = validate_plan(_plan())
    assert not r.warnings


def test_validation_logs_event(monkeypatch):
    calls = []

    def fake_info(event, **kwargs):
        calls.append(event)

    import sunny.core.orchestrator.validator as v

    monkeypatch.setattr(v.log, "info", fake_info)
    validate_plan(_plan())
    assert "plan_validated" in calls


def test_validate_missing_required_param_fails():
    p = _plan(steps=[_step(plugin="files", action="write_file", params={"path": "x"})])
    r = validate_plan(p)
    assert not r.valid
    assert any("content" in e for e in r.errors)


def test_validate_all_required_params_present_passes():
    p = _plan(steps=[_step(plugin="files", action="write_file", params={"path": "x", "content": "y"})])
    r = validate_plan(p)
    assert r.valid


def test_validate_optional_params_not_required():
    p = _plan(steps=[_step(plugin="vision", action="screenshot", params={})])
    r = validate_plan(p)
    assert r.valid


def test_validate_action_with_no_required_params():
    p = _plan(steps=[_step(plugin="os_control", action="list_processes", params={})])
    r = validate_plan(p)
    assert r.valid


# ---------------------------------------------------------------------------
# Tests para describe_screen y analyze_screen en el catálogo
# ---------------------------------------------------------------------------


def test_validate_describe_screen_no_required_params():
    p = _plan(
        intent="vision",
        steps=[_step(plugin="vision", action="describe_screen", params={})],
    )
    r = validate_plan(p)
    assert r.valid
    assert not r.effective_requires_confirmation


def test_validate_describe_screen_accepts_region_param():
    p = _plan(
        intent="vision",
        steps=[_step(plugin="vision", action="describe_screen", params={"region": None})],
    )
    r = validate_plan(p)
    assert r.valid


def test_validate_analyze_screen_requires_question():
    p = _plan(
        intent="vision",
        steps=[_step(plugin="vision", action="analyze_screen", params={})],
    )
    r = validate_plan(p)
    assert not r.valid
    assert any("question" in e for e in r.errors)


def test_validate_analyze_screen_with_question_passes():
    p = _plan(
        intent="vision",
        steps=[
            _step(
                plugin="vision",
                action="analyze_screen",
                params={"question": "¿qué ves?"},
            )
        ],
    )
    r = validate_plan(p)
    assert r.valid


def test_validate_analyze_screen_does_not_require_confirmation():
    p = _plan(
        intent="vision",
        steps=[
            _step(
                plugin="vision",
                action="analyze_screen",
                params={"question": "¿qué ves?"},
            )
        ],
    )
    r = validate_plan(p)
    assert not r.effective_requires_confirmation


# ---------------------------------------------------------------------------
# Tests para visión reactiva y agent_loop
# ---------------------------------------------------------------------------


def test_validator_accepts_wait_for_screen_text():
    p = _plan(
        intent="vision",
        steps=[
            _step(
                plugin="vision",
                action="wait_for_screen_text",
                params={"text": "PLAY", "timeout_sec": 30},
            )
        ],
    )
    r = validate_plan(p)
    assert r.valid


def test_validator_wait_for_screen_text_requires_text():
    p = _plan(
        intent="vision",
        steps=[
            _step(plugin="vision", action="wait_for_screen_text", params={})
        ],
    )
    r = validate_plan(p)
    assert not r.valid
    assert any("text" in e for e in r.errors)


def test_validator_accepts_get_screen_state():
    p = _plan(
        intent="vision",
        steps=[_step(plugin="vision", action="get_screen_state", params={})],
    )
    r = validate_plan(p)
    assert r.valid


def test_validator_accepts_agent_loop_run():
    p = _plan(
        intent="agent_loop",
        steps=[
            _step(
                plugin="agent_loop",
                action="run",
                params={"goal": "abrir factorio", "max_steps": 10},
            )
        ],
    )
    r = validate_plan(p)
    assert r.valid


def test_validator_agent_loop_requires_goal():
    p = _plan(
        intent="agent_loop",
        steps=[_step(plugin="agent_loop", action="run", params={})],
    )
    r = validate_plan(p)
    assert not r.valid
    assert any("goal" in e for e in r.errors)


def test_validator_rejects_unknown_agent_loop_action():
    p = _plan(
        intent="agent_loop",
        steps=[
            _step(plugin="agent_loop", action="explore", params={"goal": "x"})
        ],
    )
    r = validate_plan(p)
    assert not r.valid


def test_validator_agent_loop_does_not_require_confirmation():
    p = _plan(
        intent="agent_loop",
        steps=[
            _step(
                plugin="agent_loop",
                action="run",
                params={"goal": "abrir factorio"},
            )
        ],
    )
    r = validate_plan(p)
    assert not r.effective_requires_confirmation
