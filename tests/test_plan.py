import pytest
from pydantic import ValidationError

from sunny.core.models.plan import (
    Step,
    PlanV2,
    ComprehensionResult,
)


def test_step_minimal_valid():
    s = Step(step_id="s1", plugin="files", action="read", params={})
    assert s.step_id == "s1"


def test_step_step_id_empty_raises():
    with pytest.raises(ValidationError):
        Step(step_id="", plugin="p", action="a", params={})


def test_step_step_id_invalid_chars_raises():
    with pytest.raises(ValidationError):
        Step(step_id="bad id@", plugin="p", action="a", params={})


def test_step_timeout_zero_raises():
    with pytest.raises(ValidationError):
        Step(step_id="s1", plugin="p", action="a", params={}, timeout_sec=0)


def test_step_timeout_above_600_raises():
    with pytest.raises(ValidationError):
        Step(step_id="s1", plugin="p", action="a", params={}, timeout_sec=601)


def test_step_default_values():
    s = Step(step_id="s1", plugin="p", action="a", params={})
    assert s.timeout_sec == 30
    assert s.continue_on_error is False
    assert s.depends_on == []


def test_plan_minimal_valid():
    plan = PlanV2(
        intent="files",
        confidence=0.9,
        steps=[Step(step_id="s1", plugin="p", action="a", params={})],
    )
    assert plan.intent == "files"


def test_plan_confidence_below_zero_raises():
    with pytest.raises(ValidationError):
        PlanV2(intent="files", confidence=-0.1, steps=[])


def test_plan_confidence_above_one_raises():
    with pytest.raises(ValidationError):
        PlanV2(intent="files", confidence=1.1, steps=[])


def test_plan_invalid_intent_raises():
    with pytest.raises(ValidationError):
        PlanV2(intent="invalid", confidence=0.5, steps=[])


def test_plan_conversation_with_steps_raises():
    with pytest.raises(ValidationError):
        PlanV2(
            intent="conversation",
            confidence=0.9,
            steps=[Step(step_id="s1", plugin="p", action="a", params={})],
        )


def test_plan_non_conversation_without_steps_raises():
    with pytest.raises(ValidationError):
        PlanV2(intent="files", confidence=0.9, steps=[])


def test_plan_non_conversation_without_steps_ok_if_clarification():
    plan = PlanV2(
        intent="files",
        confidence=0.9,
        steps=[],
        needs_clarification=True,
    )
    assert plan.needs_clarification is True


def test_plan_duplicate_step_id_raises():
    with pytest.raises(ValidationError):
        PlanV2(
            intent="files",
            confidence=0.9,
            steps=[
                Step(step_id="s1", plugin="p", action="a", params={}),
                Step(step_id="s1", plugin="p", action="b", params={}),
            ],
        )


def test_plan_depends_on_missing_step_raises():
    with pytest.raises(ValidationError):
        PlanV2(
            intent="files",
            confidence=0.9,
            steps=[
                Step(step_id="s1", plugin="p", action="a", params={}, depends_on=["s2"])
            ],
        )


def test_plan_depends_on_self_raises():
    with pytest.raises(ValidationError):
        PlanV2(
            intent="files",
            confidence=0.9,
            steps=[
                Step(step_id="s1", plugin="p", action="a", params={}, depends_on=["s1"])
            ],
        )


def test_plan_depends_on_valid_chain_ok():
    plan = PlanV2(
        intent="files",
        confidence=0.9,
        steps=[
            Step(step_id="s1", plugin="p", action="a", params={}),
            Step(step_id="s2", plugin="p", action="b", params={}, depends_on=["s1"]),
            Step(
                step_id="s3",
                plugin="p",
                action="c",
                params={},
                depends_on=["s1", "s2"],
            ),
        ],
    )
    assert len(plan.steps) == 3


def test_plan_serializes_to_dict():
    plan = PlanV2(
        intent="files",
        confidence=0.9,
        steps=[Step(step_id="s1", plugin="p", action="a", params={})],
    )
    data = plan.model_dump()
    plan2 = PlanV2.model_validate(data)
    assert plan2.intent == plan.intent


def test_plan_serializes_to_json():
    plan = PlanV2(
        intent="files",
        confidence=0.9,
        steps=[Step(step_id="s1", plugin="p", action="a", params={})],
    )
    data = plan.model_dump_json()
    plan2 = PlanV2.model_validate_json(data)
    assert plan2.intent == plan.intent


def test_comprehension_minimal_valid():
    c = ComprehensionResult(
        comprehension="test",
        intent="files",
        confidence=0.8,
    )
    assert c.intent == "files"


def test_comprehension_invalid_intent_raises():
    with pytest.raises(ValidationError):
        ComprehensionResult(
            comprehension="test",
            intent="invalid",
            confidence=0.8,
        )


def test_comprehension_confidence_out_of_range_raises():
    with pytest.raises(ValidationError):
        ComprehensionResult(
            comprehension="test",
            intent="files",
            confidence=1.5,
        )


def test_comprehension_assumptions_default_empty_list():
    c = ComprehensionResult(
        comprehension="test",
        intent="files",
        confidence=0.5,
    )
    assert c.assumptions == []
