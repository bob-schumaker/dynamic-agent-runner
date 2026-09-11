"""Regression boundary for scenario-neutral embedding production source."""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).parents[1]
_FORBIDDEN = (
    "gte-tiny",
    "mlx_gte_tiny",
    "MLXGteTiny",
    "TaylorAI/gte-tiny",
)


def test_production_source_has_no_named_embedding_experiment() -> None:
    for path in _ROOT.joinpath("src").rglob("*.py"):
        contents = path.read_text(encoding="utf-8")
        assert all(value not in contents for value in _FORBIDDEN), path
