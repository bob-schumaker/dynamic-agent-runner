from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_dms20_batch import pad_token_ids


def test_pad_token_ids_keeps_prompts_aligned() -> None:
    assert pad_token_ids([[4, 5, 6], [7]], 0) == (
        [[4, 5, 6], [7, 0, 0]],
        [[1, 1, 1], [1, 0, 0]],
    )


@pytest.mark.parametrize("rows", [[], [[]], [[1], []]])
def test_pad_token_ids_rejects_empty_batches_or_prompts(rows: list[list[int]]) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        pad_token_ids(rows, 0)
