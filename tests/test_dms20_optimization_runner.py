"""Fake-backed checks for the separately approved Kev MPS pilot."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms20_optimization import OptimizationRunError, _compare_smoke, _load_kev_mps


class FakeChoice:
    def __init__(self, **values: object) -> None:
        self.values = values


class FakeModel:
    def eval(self) -> FakeModel:
        return self

    def encode(self, _tokenizer: object, record: object, **_kwargs: object) -> object:
        return record

    def probs(self, _encoded: object) -> list[list[float]]:
        return [FakeTensor([0.25, 0.75])]  # type: ignore[list-item]


class FakeTensor(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class FakeCheckpoint:
    loaded: tuple[str, object] | None = None

    def __init__(self, _requested: str) -> None:
        self.meta = type(
            "Meta", (), {"base": "Qwen/Qwen3.5-4B-Base", "base_revision": "base-rev"}
        )()

    def load(self, device: str, options: object) -> tuple[object, FakeModel]:
        type(self).loaded = (device, options)
        return object(), FakeModel()


def _fake_modules(monkeypatch: pytest.MonkeyPatch) -> FakeCheckpoint:
    torch = ModuleType("torch")
    torch.bfloat16 = "bfloat16"  # type: ignore[attr-defined]
    torch.float32 = "float32"  # type: ignore[attr-defined]
    torch.inference_mode = nullcontext  # type: ignore[attr-defined]
    torch.backends = type(
        "Backends",
        (),
        {"mps": type("MPS", (), {"is_available": staticmethod(lambda: True)})},
    )()
    torch.mps = type("MPS", (), {"synchronize": staticmethod(lambda: None)})()

    api = ModuleType("kev.api")
    api.Choice = FakeChoice  # type: ignore[attr-defined]
    api.SystemOneRequest = lambda **values: values  # type: ignore[attr-defined]
    api.to_record = lambda request: (request, [{"keys": ["a", "b"]}])  # type: ignore[attr-defined]

    model_module = ModuleType("kev.model")
    model_module.SERVE_MAX_BRANCH = 8192  # type: ignore[attr-defined]
    model_module.SERVE_MAX_STATE = 8192  # type: ignore[attr-defined]

    checkpoint_module = ModuleType("kev.checkpoint")
    checkpoint_module.Checkpoint = FakeCheckpoint  # type: ignore[attr-defined]

    class LoadOptions:
        def __init__(self, **values: object) -> None:
            self.values = values

    checkpoint_module.LoadOptions = LoadOptions  # type: ignore[attr-defined]
    kev = ModuleType("kev")
    kev.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "kev", kev)
    monkeypatch.setitem(sys.modules, "kev.api", api)
    monkeypatch.setitem(sys.modules, "kev.model", model_module)
    monkeypatch.setitem(sys.modules, "kev.checkpoint", checkpoint_module)
    return FakeCheckpoint


def test_kev_mps_loader_selects_bf16_torch_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkpoint_type = _fake_modules(monkeypatch)
    row = {
        "model": {"id": "jaredpalmer/kev-4b", "revision": "model-rev"},
        "base_model": {"id": "Qwen/Qwen3.5-4B-Base", "revision": "base-rev"},
    }

    infer, _token_count, model = _load_kev_mps(row, tmp_path)

    assert checkpoint_type.loaded is not None
    assert checkpoint_type.loaded[0] == "mps"
    assert checkpoint_type.loaded[1].values == {
        "dtype": "bfloat16",
        "merge": True,
        "attn": "sdpa",
        "backend": "torch",
    }
    result = infer(
        {
            "state": {"text": "state"},
            "question": {
                "id": "decision",
                "text": "Choose.",
                "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            },
        }
    )
    assert result["choice"] == "b"
    assert result["scores"] == {"a": 0.25, "b": 0.75}
    assert model.__class__ is FakeModel


def test_smoke_gate_stops_when_any_choice_differs() -> None:
    with pytest.raises(OptimizationRunError, match="choice parity"):
        _compare_smoke(
            [{"id": "mmlu/test/1", "option_order": "canonical", "choice": "a"}],
            [{"id": "mmlu/test/1", "option_order": "canonical", "choice": "b"}],
        )
