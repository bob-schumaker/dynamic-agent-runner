"""Internal graph-mutation protocols and datamodels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from dynamic_agent_runner.models import CompiledAgentWorkflow, LoadedAgentWorkflow


WorkflowLike = "LoadedAgentWorkflow | CompiledAgentWorkflow | object"


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
