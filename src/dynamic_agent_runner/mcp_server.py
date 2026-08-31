"""DAR's generic stdio MCP entry point for configured workflow hosts."""

from dynamic_agent_runner.workflow_host.server import console_main, main

__all__ = ("console_main", "main")


if __name__ == "__main__":  # pragma: no cover - exercised by subprocess smoke test.
    console_main()
