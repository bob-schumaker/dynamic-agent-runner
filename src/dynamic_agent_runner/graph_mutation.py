"""Internal graph-mutation protocols, datamodels, and derivation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from dynamic_agent_runner.models import CompiledAgentWorkflow, LoadedAgentWorkflow


@dataclass(frozen=True)
class GraphMutationSpec:
    """Repository-owned internal description of one graph mutation target."""

    mutation_id: str
    kind: str
    target_node_id: str | None = None
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowMutationBundle:
    """Collection of internal mutation specs derived for one workflow."""

    mutations: tuple[GraphMutationSpec, ...] = ()

    @property
    def mutation_ids(self) -> tuple[str, ...]:
        """Return stable mutation ids in bundle order."""

        return tuple(spec.mutation_id for spec in self.mutations)

    def for_node(self, node_id: str) -> tuple[GraphMutationSpec, ...]:
        """Return mutation specs targeting the given node id."""

        return tuple(spec for spec in self.mutations if spec.target_node_id == node_id)


@dataclass(frozen=True)
class MutationResult:
    """Result of applying one or more internal workflow mutations."""

    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | object
    bundle: WorkflowMutationBundle = field(default_factory=WorkflowMutationBundle)
    notices: tuple[str, ...] = ()


class WorkflowGraphMutation(Protocol):
    """Internal protocol for derived graph-mutation behavior."""

    mutation_id: str

    def apply(
        self, workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | object
    ) -> MutationResult:
        """Apply the mutation to a workflow-like object and return diagnostics."""


def derive_workflow_mutation_bundle(
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | object,
) -> WorkflowMutationBundle:
    """Derive internal mutation specs from eligible workflow node metadata."""

    manifest = getattr(workflow, "runtime_manifest", None)
    nodes = getattr(manifest, "nodes", ()) if manifest is not None else ()
    mutations = tuple(
        spec
        for spec in (_derive_node_mutation_spec(node) for node in nodes)
        if spec is not None
    )
    return WorkflowMutationBundle(mutations=mutations)


def _derive_node_mutation_spec(node: object) -> GraphMutationSpec | None:
    """Return the first-slice mutation spec for an eligible runtime node."""

    node_id = getattr(node, "id", None)
    kind = getattr(node, "kind", None)
    raw = getattr(node, "raw", None)
    if not node_id or kind != "llm_step" or not isinstance(raw, Mapping):
        return None

    context_pipeline = raw.get("context_pipeline")
    if (
        not isinstance(context_pipeline, Mapping)
        or context_pipeline.get("enabled") is not True
    ):
        return None

    return GraphMutationSpec(
        mutation_id=f"context-pruning-{node_id}",
        kind="context_pruning",
        target_node_id=str(node_id),
        config={
            "context_pipeline": dict(context_pipeline),
            "context_sources": tuple(_mapping_items(raw.get("context_sources"))),
            "context_contract": dict(_as_mapping(raw.get("context_contract")) or {}),
        },
    )


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _mapping_items(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
