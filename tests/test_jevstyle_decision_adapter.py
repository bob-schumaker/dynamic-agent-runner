from __future__ import annotations

import pytest

from dynamic_agent_runner.decision_models import (
    DecisionMode,
    DecisionModelBinding,
    DecisionModelRequest,
    DecisionModelUse,
    DecisionOption,
    DecisionQuestion,
    DecisionScoreSemantics,
    validate_decision_result,
)
from dynamic_agent_runner.workflow_host.jevstyle_decision_adapter import (
    JEVSTYLE_V3_GGUF_PROFILE,
    JEVSTYLE_V3_MLX_PROFILE,
    JEVSTYLE_V3_TORCH_PROFILE,
    JevStyleAdapterError,
    JevStyleBackend,
    JevStyleMachineConfiguration,
    JevStyleModelCandidate,
    JevStyleV3DecisionAdapter,
    load_jevstyle_v3_binding,
    select_jevstyle_candidate,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)


class FakeEngine:
    def __init__(self, answers: dict[str, dict[str, object]]) -> None:
        self.answers = answers
        self.calls: list[tuple[object, dict[str, object]]] = []

    def decide(self, state: object, question: dict[str, object]) -> dict[str, object]:
        self.calls.append((state, question))
        answer = self.answers.get(str(question["t"]))
        if answer is None:
            return self.answers["default"]
        return answer


def _candidate(backend, profile, loader, *, materials=True, resources=True):
    return JevStyleModelCandidate(
        backend=backend,
        profile=profile,
        execution_binding=ModelExecutionBinding(
            logical_model_id=profile.identity.model_id,
            runner_contract_id=f"jevstyle-{backend.value}",
            runner_contract_version="1",
            loader_profile_contract_id=f"jevstyle-{backend.value}-loader",
            loader_profile_contract_version="1",
            material_lock_digest="a" * 64,
            capability_requirements_digest="b" * 64,
            runner_capability_id=f"jevstyle-{backend.value}",
            runner_capability_version="1",
            runner_capability_digest="c" * 64,
        ),
        materials_admitted=materials,
        resource_admitted=resources,
        load_engine=lambda _binding: loader(),
    )


def _machine(*, platform="darwin", architecture="arm64", metal=True):
    return JevStyleMachineConfiguration(
        platform=platform,
        architecture=architecture,
        metal_available=metal,
    )


def _request(mode, ids=("yes", "no")):
    return DecisionModelRequest(
        decision_id="test-decision",
        context={"ticket": "duplicate charge"},
        questions=(
            DecisionQuestion(
                id="answer",
                options=tuple(DecisionOption(value, value.title()) for value in ids),
                text="Should this be retained?",
            ),
        ),
        mode=mode,
    )


def test_selector_prefers_mlx_only_on_eligible_apple_silicon() -> None:
    loaders = {"mlx": 0, "gguf": 0, "torch": 0}
    candidates = (
        _candidate(
            JevStyleBackend.MLX,
            JEVSTYLE_V3_MLX_PROFILE,
            lambda: loaders.__setitem__("mlx", loaders["mlx"] + 1),
        ),
        _candidate(
            JevStyleBackend.GGUF,
            JEVSTYLE_V3_GGUF_PROFILE,
            lambda: loaders.__setitem__("gguf", loaders["gguf"] + 1),
        ),
        _candidate(
            JevStyleBackend.TORCH,
            JEVSTYLE_V3_TORCH_PROFILE,
            lambda: loaders.__setitem__("torch", loaders["torch"] + 1),
        ),
    )

    selected = select_jevstyle_candidate(_machine(), candidates)

    assert selected.backend is JevStyleBackend.MLX
    assert loaders == {"mlx": 0, "gguf": 0, "torch": 0}


def test_selector_rejects_invalid_machine_configuration() -> None:
    with pytest.raises(JevStyleAdapterError, match="machine configuration"):
        select_jevstyle_candidate("darwin", ())


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        (_machine(metal=False), JevStyleBackend.GGUF),
        (
            _machine(platform="linux", architecture="x86_64", metal=False),
            JevStyleBackend.GGUF,
        ),
    ],
)
def test_selector_prefers_gguf_for_cpu(
    machine: JevStyleMachineConfiguration, expected: JevStyleBackend
) -> None:
    candidates = (
        _candidate(JevStyleBackend.GGUF, JEVSTYLE_V3_GGUF_PROFILE, lambda: None),
        _candidate(JevStyleBackend.TORCH, JEVSTYLE_V3_TORCH_PROFILE, lambda: None),
    )

    assert select_jevstyle_candidate(machine, candidates).backend is expected


def test_selector_uses_torch_cpu_when_gguf_is_unavailable() -> None:
    candidates = (
        _candidate(JevStyleBackend.TORCH, JEVSTYLE_V3_TORCH_PROFILE, lambda: None),
    )

    assert (
        select_jevstyle_candidate(_machine(metal=False), candidates).backend
        is JevStyleBackend.TORCH
    )


def test_candidate_rejects_execution_binding_for_another_model() -> None:
    candidate = _candidate(JevStyleBackend.GGUF, JEVSTYLE_V3_GGUF_PROFILE, lambda: None)
    wrong_binding = ModelExecutionBinding(
        **{
            **candidate.execution_binding.__dict__,
            "logical_model_id": "another/model",
        }
    )

    with pytest.raises(JevStyleAdapterError, match="candidate binding"):
        JevStyleModelCandidate(
            backend=JevStyleBackend.GGUF,
            profile=JEVSTYLE_V3_GGUF_PROFILE,
            execution_binding=wrong_binding,
            materials_admitted=True,
            resource_admitted=True,
            load_engine=lambda _binding: None,
        )


def test_selector_skips_unadmitted_profiles_and_fails_before_loading_if_none() -> None:
    calls = []
    candidates = (
        _candidate(
            JevStyleBackend.MLX,
            JEVSTYLE_V3_MLX_PROFILE,
            lambda: calls.append("mlx"),
            resources=False,
        ),
        _candidate(
            JevStyleBackend.GGUF,
            JEVSTYLE_V3_GGUF_PROFILE,
            lambda: calls.append("gguf"),
            materials=False,
        ),
    )

    with pytest.raises(JevStyleAdapterError, match="no admitted Jev-Style profile"):
        select_jevstyle_candidate(_machine(), candidates)

    assert calls == []


def test_selected_loader_is_called_once_and_load_failure_never_falls_back() -> None:
    calls = []
    candidates = (
        _candidate(
            JevStyleBackend.MLX,
            JEVSTYLE_V3_MLX_PROFILE,
            lambda: (
                calls.append("mlx"),
                (_ for _ in ()).throw(RuntimeError("broken")),
            )[1],
        ),
        _candidate(
            JevStyleBackend.GGUF,
            JEVSTYLE_V3_GGUF_PROFILE,
            lambda: calls.append("gguf"),
        ),
    )

    with pytest.raises(
        JevStyleAdapterError, match="selected Jev-Style backend failed to load"
    ):
        load_jevstyle_v3_binding(_machine(), candidates)

    assert calls == ["mlx"]


def test_selected_adapter_maps_choice_and_has_exact_profile_binding() -> None:
    engine = FakeEngine(
        {"choice": {"answer": "yes", "probabilities": {"yes": 0.8, "no": 0.2}}}
    )
    candidates = (
        _candidate(JevStyleBackend.GGUF, JEVSTYLE_V3_GGUF_PROFILE, lambda: engine),
    )

    binding = load_jevstyle_v3_binding(_machine(metal=False), candidates)
    request = _request(DecisionMode.CHOICE)
    result = binding.adapter.decide(request)

    assert isinstance(binding, DecisionModelBinding)
    assert binding.profile is JEVSTYLE_V3_GGUF_PROFILE
    assert binding.adapter.material_lock_digest == "a" * 64
    assert binding.permitted_uses == frozenset({DecisionModelUse.WORKFLOW_DECISION})
    assert result.identity == JEVSTYLE_V3_GGUF_PROFILE.identity
    assert result.results[0].choice == "yes"
    assert engine.calls[0][1] == {
        "t": "choice",
        "ins": "Should this be retained?",
        "crit": {"yes": "Yes", "no": "No"},
    }
    validate_decision_result(result, request, JEVSTYLE_V3_GGUF_PROFILE)


def test_adapter_rejects_choice_outside_the_declared_option_set() -> None:
    adapter = JevStyleV3DecisionAdapter(
        FakeEngine(
            {"choice": {"answer": "other", "probabilities": {"a": 0.8, "b": 0.2}}}
        ),
        JEVSTYLE_V3_GGUF_PROFILE,
    )

    with pytest.raises(JevStyleAdapterError, match="selected option"):
        adapter.decide(_request(DecisionMode.CHOICE, ("a", "b")))


def test_jevstyle_binding_rejects_context_retention_use() -> None:
    engine = FakeEngine(
        {"choice": {"answer": "a", "probabilities": {"a": 0.8, "b": 0.2}}}
    )
    binding = load_jevstyle_v3_binding(
        _machine(metal=False),
        (_candidate(JevStyleBackend.GGUF, JEVSTYLE_V3_GGUF_PROFILE, lambda: engine),),
    )

    with pytest.raises(ValueError, match="unsupported use"):
        DecisionModelBinding(
            profile=binding.profile,
            adapter=binding.adapter,
            permitted_uses=frozenset({DecisionModelUse.CONTEXT_RETENTION}),
        )

    assert engine.calls == []


def test_selected_engine_loader_receives_host_material_execution_binding() -> None:
    engine = FakeEngine(
        {"choice": {"answer": "yes", "probabilities": {"yes": 0.8, "no": 0.2}}}
    )
    received = []
    base = _candidate(JevStyleBackend.GGUF, JEVSTYLE_V3_GGUF_PROFILE, lambda: engine)
    candidate = JevStyleModelCandidate(
        backend=base.backend,
        profile=base.profile,
        execution_binding=base.execution_binding,
        materials_admitted=True,
        resource_admitted=True,
        load_engine=lambda binding: (received.append(binding), engine)[1],
    )

    binding = load_jevstyle_v3_binding(_machine(metal=False), (candidate,))
    binding.adapter.decide(_request(DecisionMode.CHOICE))

    assert received == [candidate.execution_binding]
    assert received[0].logical_model_id == binding.profile.identity.model_id
    assert binding.adapter.material_lock_digest == received[0].material_lock_digest


@pytest.mark.parametrize(
    ("ids", "probabilities", "expected"),
    [
        (("yes", "no"), {"false": 0.25, "true": 0.75}, (0.75, 0.25)),
        (("no", "yes"), {"false": 0.25, "true": 0.75}, (0.25, 0.75)),
    ],
)
def test_noul_maps_to_scores_in_request_order(ids, probabilities, expected) -> None:
    engine = FakeEngine({"noul": {"answer": "true", "probabilities": probabilities}})
    adapter = JevStyleV3DecisionAdapter(engine, JEVSTYLE_V3_MLX_PROFILE)
    request = _request(DecisionMode.SCORES, ids)

    result = adapter.decide(request)

    assert tuple(score.value for score in result.results[0].scores) == pytest.approx(
        expected
    )
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY
    assert engine.calls[0][1]["t"] == "noul"
    validate_decision_result(result, request, JEVSTYLE_V3_MLX_PROFILE)


def test_score_probabilities_map_from_ordered_indexes_to_option_ids() -> None:
    engine = FakeEngine(
        {"score": {"answer": "1", "probabilities": {"0": 0.2, "1": 0.8}}}
    )
    adapter = JevStyleV3DecisionAdapter(engine, JEVSTYLE_V3_TORCH_PROFILE)
    request = _request(DecisionMode.SCORES, ("low", "high"))

    result = adapter.decide(request)

    assert [score.option_id for score in result.results[0].scores] == ["low", "high"]
    assert [score.value for score in result.results[0].scores] == pytest.approx(
        [0.2, 0.8]
    )
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY
    validate_decision_result(result, request, JEVSTYLE_V3_TORCH_PROFILE)


def test_adapter_supports_mlx_decide_many_runtime_interface() -> None:
    class BatchOnlyEngine:
        def decide_many(self, state, questions):
            self.call = (state, questions)
            return [
                {
                    "answer": "true",
                    "probabilities": {"false": 0.2, "true": 0.8},
                }
            ]

    engine = BatchOnlyEngine()
    adapter = JevStyleV3DecisionAdapter(engine, JEVSTYLE_V3_MLX_PROFILE)
    request = _request(DecisionMode.SCORES)

    result = adapter.decide(request)

    assert engine.call[1] == [
        {
            "t": "noul",
            "ins": "Should this be retained?",
            "crit": {"false": "No", "true": "Yes"},
        }
    ]
    assert result.results[0].scores[0].value == pytest.approx(0.8)


@pytest.mark.parametrize(
    "probabilities",
    [
        {"yes": 0.5},
        {"yes": float("nan"), "no": 0.5},
        {"yes": 1.5, "no": -0.5},
        {"yes": 0.2, "no": 0.2},
    ],
)
def test_adapter_rejects_invalid_or_incomplete_probabilities(probabilities) -> None:
    adapter = JevStyleV3DecisionAdapter(
        FakeEngine({"choice": {"answer": "yes", "probabilities": probabilities}}),
        JEVSTYLE_V3_MLX_PROFILE,
    )

    with pytest.raises(ValueError, match="probabilities"):
        adapter.decide(_request(DecisionMode.CHOICE))


def test_optional_runtime_loader_is_never_called_for_unselected_backend() -> None:
    calls = []
    candidates = (
        _candidate(
            JevStyleBackend.MLX,
            JEVSTYLE_V3_MLX_PROFILE,
            lambda: (
                calls.append("mlx"),
                FakeEngine(
                    {"choice": {"answer": "a", "probabilities": {"a": 1.0, "b": 0.0}}}
                ),
            )[1],
        ),
        _candidate(
            JevStyleBackend.GGUF,
            JEVSTYLE_V3_GGUF_PROFILE,
            lambda: (
                calls.append("gguf"),
                FakeEngine(
                    {"choice": {"answer": "a", "probabilities": {"a": 1.0, "b": 0.0}}}
                ),
            )[1],
        ),
    )

    binding = load_jevstyle_v3_binding(_machine(), candidates)
    binding.adapter.decide(_request(DecisionMode.CHOICE, ("a", "b")))

    assert calls == ["mlx"]


def test_inference_failure_does_not_load_another_backend() -> None:
    calls = []

    class BrokenEngine:
        def decide(self, _state, _question):
            raise RuntimeError("private model error")

    candidates = (
        _candidate(
            JevStyleBackend.MLX,
            JEVSTYLE_V3_MLX_PROFILE,
            lambda: (calls.append("mlx-load"), BrokenEngine())[1],
        ),
        _candidate(
            JevStyleBackend.GGUF,
            JEVSTYLE_V3_GGUF_PROFILE,
            lambda: calls.append("gguf-load"),
        ),
    )
    binding = load_jevstyle_v3_binding(_machine(), candidates)

    with pytest.raises(JevStyleAdapterError, match="inference failed") as error:
        binding.adapter.decide(_request(DecisionMode.CHOICE))

    assert "private model error" not in str(error.value)
    assert str(error.value.__cause__) == "private model error"
    assert calls == ["mlx-load"]
