"""Focused unit tests for internal graph-mutation datamodels."""

from __future__ import annotations

from dynamic_agent_runner.graph_mutation import (
    GraphMutationSpec,
    MutationResult,
    WorkflowGraphMutation,
    WorkflowMutationBundle,
)


def test_workflow_mutation_bundle_can_describe_context_pruning_target() -> None:
    """The internal bundle can represent the first context-pruning attachment."""

    spec = GraphMutationSpec(
        mutation_id="context-pruning-answer",
        kind="context_pruning",
        target_node_id="answer",
        config={
            "context_pipeline": {
                "enabled": True,
                "strategy": "semantic_pruning",
                "profile": "default",
            },
            "context_sources": (
                {
                    "kind": "conversation_history",
                    "source": "state.chat_history",
                },
                {
                    "kind": "latest_user_prompt",
                    "source": "prompt",
                },
            ),
            "context_contract": {
                "history_input": "state.chat_history",
                "current_prompt_input": "prompt",
                "output_slot": "prepared_context",
            },
        },
    )

    bundle = WorkflowMutationBundle(mutations=(spec,))

    assert bundle.mutations == (spec,)
    assert bundle.mutation_ids == ("context-pruning-answer",)
    assert bundle.for_node("answer") == (spec,)


def test_mutation_result_preserves_workflow_and_notices() -> None:
    """Mutation results carry the unchanged workflow reference and diagnostics."""

    workflow = object()
    result = MutationResult(
        workflow=workflow,
        bundle=WorkflowMutationBundle(),
        notices=("context pipeline attached",),
    )

    assert result.workflow is workflow
    assert result.bundle.mutations == ()
    assert result.notices == ("context pipeline attached",)


def test_workflow_graph_mutation_protocol_supports_apply_contract() -> None:
    """Mutation implementations satisfy the repository-owned apply protocol."""

    class StubMutation:
        mutation_id = "context-pruning"

        def apply(self, workflow: object) -> MutationResult:
            return MutationResult(workflow=workflow, bundle=WorkflowMutationBundle())

    mutation: WorkflowGraphMutation = StubMutation()
    workflow = object()

    assert mutation.mutation_id == "context-pruning"
    assert mutation.apply(workflow).workflow is workflow
