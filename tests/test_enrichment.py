from __future__ import annotations

import sys
import types

import pytest

from sunny.core.models.plan import ComprehensionResult
from sunny.core.orchestrator import enrichment, planner


def _comp(intent: str = "agent_loop", text: str = "abrir spotify y poner una canción") -> ComprehensionResult:
    return ComprehensionResult(
        comprehension=text,
        intent=intent,
        assumptions=[],
        confidence=0.9,
        needs_clarification=False,
    )


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeUsage:
    def __init__(self, prompt_tokens: int = 12, completion_tokens: int = 34) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, content: str = "1. clic en buscar\n2. escribe la canción\n3. enter", raise_exc: Exception | None = None) -> None:
        self._content = content
        self._raise = raise_exc
        self.last_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise is not None:
            raise self._raise
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeGroqClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)


def _install_fake_groq(monkeypatch, completions: _FakeCompletions) -> None:
    fake_module = types.ModuleType("groq")
    fake_module.Groq = lambda api_key=None, **_: _FakeGroqClient(completions)
    monkeypatch.setitem(sys.modules, "groq", fake_module)


def test_enrich_skips_non_agent_loop(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "irrelevant")
    # Si llegara a importar groq sería un fallo silencioso pero el intent corta antes.
    monkeypatch.delitem(sys.modules, "groq", raising=False)
    out = enrichment.enrich(_comp(intent="files"), "lee notas.txt")
    assert out is None


def test_enrich_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = enrichment.enrich(_comp(intent="agent_loop"), "abrir spotify")
    assert out is None


def test_enrich_returns_guidance(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    completions = _FakeCompletions(content="1. abre spotify\n2. busca la canción\n3. clic en play")
    _install_fake_groq(monkeypatch, completions)

    events = []

    def fake_info(*args, **kwargs):
        events.append((args, kwargs))

    monkeypatch.setattr(enrichment.log, "info", fake_info)

    out = enrichment.enrich(_comp(intent="agent_loop"), "abrir spotify y poner bohemian rhapsody")
    assert out is not None
    assert "play" in out
    assert completions.last_kwargs["model"]
    assert completions.last_kwargs["temperature"] == 0.1

    event_names = [
        kwargs.get("event") if "event" in kwargs else (args[0] if args else None)
        for args, kwargs in events
    ]
    assert "enrichment_done" in event_names


def test_enrich_returns_none_on_failure(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    completions = _FakeCompletions(raise_exc=RuntimeError("boom"))
    _install_fake_groq(monkeypatch, completions)

    out = enrichment.enrich(_comp(intent="agent_loop"), "abrir spotify")
    assert out is None


def test_enrich_returns_none_on_empty_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    completions = _FakeCompletions(content="")
    _install_fake_groq(monkeypatch, completions)

    out = enrichment.enrich(_comp(intent="agent_loop"), "abrir spotify")
    assert out is None


def test_build_planning_prompt_includes_guidance():
    prompt = planner.build_planning_user_prompt(
        "abrir spotify",
        _comp(intent="agent_loop"),
        context=None,
        guidance="1. clic en buscar\n2. escribe canción",
    )
    assert planner.GUIDANCE_TAG in prompt
    assert "1. clic en buscar" in prompt
    # Orden: GUÍA PREVIA antes de COMPRENSIÓN PREVIA
    assert prompt.find(planner.GUIDANCE_TAG) < prompt.find(planner.COMPREHENSION_TAG)


def test_build_planning_prompt_no_guidance():
    prompt = planner.build_planning_user_prompt(
        "abrir spotify",
        _comp(intent="agent_loop"),
        context=None,
        guidance=None,
    )
    assert planner.GUIDANCE_TAG not in prompt


from sunny.brain.ollama_client import LLMCallStats
from sunny.core.models.plan import PlanV2, Step


def _fake_planv2(intent: str = "agent_loop") -> PlanV2:
    if intent == "files":
        return PlanV2(
            intent="files",
            confidence=0.9,
            needs_clarification=False,
            requires_confirmation=False,
            steps=[
                Step(
                    step_id="s1",
                    plugin="files",
                    action="read_file",
                    params={"path": "C:\\test.txt"},
                )
            ],
        )
    return PlanV2(
        intent="agent_loop",
        confidence=0.85,
        needs_clarification=False,
        requires_confirmation=False,
        steps=[
            Step(
                step_id="s1",
                plugin="agent_loop",
                action="run",
                params={"goal": "x", "max_steps": 10},
                timeout_sec=300,
            )
        ],
    )


class _FakeProvider:
    def __init__(self, plan: PlanV2) -> None:
        self._plan = plan
        self.last_user_prompt: str = ""

    def call_validated(self, user_prompt, system_prompt, schema):
        self.last_user_prompt = user_prompt
        return self._plan, LLMCallStats(tokens_in=50, tokens_out=100, latency_ms=1, retries_used=0)


def test_plan_calls_enrich_for_agent_loop(monkeypatch):
    calls = []

    def fake_enrich(comp, user_input):
        calls.append((comp.intent, user_input))
        return "guía simulada"

    monkeypatch.setattr(planner, "enrich", fake_enrich)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    fake_provider = _FakeProvider(_fake_planv2("agent_loop"))
    monkeypatch.setattr(planner, "get_provider_for_role", lambda role: fake_provider)

    planner.plan("abrir spotify", _comp(intent="agent_loop"))

    assert len(calls) == 1
    assert calls[0][0] == "agent_loop"
    assert planner.GUIDANCE_TAG in fake_provider.last_user_prompt
    assert "guía simulada" in fake_provider.last_user_prompt


def test_plan_skips_enrich_for_other_intents(monkeypatch):
    called = []

    def fake_enrich(comp, user_input):
        called.append(True)
        return "no debería usarse"

    monkeypatch.setattr(planner, "enrich", fake_enrich)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    fake_provider = _FakeProvider(_fake_planv2("files"))
    monkeypatch.setattr(planner, "get_provider_for_role", lambda role: fake_provider)

    planner.plan("lee notas.txt", _comp(intent="files"))

    assert called == []
    assert planner.GUIDANCE_TAG not in fake_provider.last_user_prompt
