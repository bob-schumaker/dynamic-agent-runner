"""The embedding extra stays separate from generation-only mlx-lm."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_mlx_embedding_extra_pins_mlx_without_mlx_lm() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert project["project"]["optional-dependencies"]["mlx-embedding"] == [
        "mlx==0.32.2; platform_system == 'Darwin'"
    ]
    assert project["tool"]["poetry"]["dependencies"]["mlx"]["version"] == "0.32.2"
    assert (
        project["tool"]["poetry"]["dependencies"]["mlx"]["markers"]
        == "platform_system == 'Darwin' and extra == 'mlx-embedding'"
    )
    assert "mlx-lm" not in project["project"]["optional-dependencies"]["mlx-embedding"]
