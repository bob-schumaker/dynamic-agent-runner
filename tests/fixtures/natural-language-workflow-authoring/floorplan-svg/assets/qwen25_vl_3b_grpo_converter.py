"""Workflow-sealed identity for DAR's trusted Qwen 2.5 VL 3B GRPO converter."""

from dynamic_agent_runner.workflow_host.qwen25_vl_3b_grpo_converter import (
    Qwen25Vl3bGrpoInputConverter,
)


converter_contract_version = "v1"
compatible_runner_contract_id = "transformers-generate-v1"
converter = Qwen25Vl3bGrpoInputConverter
