from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from dynamic_agent_runner.cli import main


def test_adapter_cli_list_accepts_state_root_after_command(tmp_path: Path) -> None:
    output = StringIO()
    result = main(
        ["adapter", "list", "--state-root", str(tmp_path)],
        stdout=output,
        stderr=StringIO(),
    )
    assert result == 0
    assert json.loads(output.getvalue()) == {"adapters": []}


def test_adapter_cli_requires_explicit_state_root() -> None:
    output = StringIO()
    result = main(["adapter", "list"], stdout=output, stderr=output)
    assert result == 1
    assert "state-root" in output.getvalue()
