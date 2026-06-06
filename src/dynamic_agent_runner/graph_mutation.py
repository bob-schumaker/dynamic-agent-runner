"""Internal graph-mutation protocols, datamodels, and derivation helpers."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from dynamic_agent_runner.openai_client import OpenAIMessage

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


@dataclass(frozen=True)
class ContextPruningMutation:
    """First live input-transform mutation for declared context-pruning metadata."""

    spec: GraphMutationSpec

    @property
    def mutation_id(self) -> str:
        """Expose the stable mutation identifier expected by orchestration."""

        return self.spec.mutation_id

    def apply(
        self, workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | object
    ) -> MutationResult:
        """Return a narrow mutation result without altering the base workflow."""

        target = self.spec.target_node_id or "<unknown>"
        return MutationResult(
            workflow=workflow,
            bundle=WorkflowMutationBundle(mutations=(self.spec,)),
            notices=(f"{self.mutation_id} ready for node {target!r}",),
        )

    def render_context(
        self,
        *,
        prompt: str,
        session_messages: Sequence[OpenAIMessage] = (),
        resolve_source: Callable[[str | None], Any] | None = None,
    ) -> dict[str, str]:
        """Render the mutation-owned output slot from declared context sources."""

        return {
            _prepared_context_output_slot(self.spec): _prepared_context_value(
                self.spec,
                prompt=prompt,
                session_messages=session_messages,
                resolve_source=resolve_source,
            )
        }


def apply_workflow_mutations(
    workflow: LoadedAgentWorkflow | CompiledAgentWorkflow | object,
    mutations: Sequence[WorkflowGraphMutation],
) -> MutationResult:
    """Apply internal workflow mutations while preserving workflow identity."""

    current_workflow = workflow
    bundle_specs: list[GraphMutationSpec] = []
    notices: list[str] = []
    for mutation in mutations:
        result = mutation.apply(current_workflow)
        current_workflow = result.workflow
        bundle_specs.extend(result.bundle.mutations)
        notices.extend(result.notices)
    return MutationResult(
        workflow=current_workflow,
        bundle=WorkflowMutationBundle(mutations=tuple(bundle_specs)),
        notices=tuple(notices),
    )


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


def _prepared_context_output_slot(spec: GraphMutationSpec) -> str:
    config = spec.config if isinstance(spec.config, Mapping) else {}
    contract = _as_mapping(config.get("context_contract")) or {}
    output_slot = contract.get("output_slot")
    return str(output_slot) if output_slot is not None else "prepared_context"


def _prepared_context_value(
    spec: GraphMutationSpec,
    *,
    prompt: str,
    session_messages: Sequence[OpenAIMessage],
    resolve_source: Callable[[str | None], Any] | None,
) -> str:
    parts = [
        _stringify_prepared_context_value(
            _resolve_prepared_context_source(
                source,
                prompt=prompt,
                session_messages=session_messages,
                resolve_source=resolve_source,
            )
        )
        for source in _prepared_context_sources(spec)
    ]
    return "\n".join(part for part in parts if part)


def _prepared_context_sources(spec: GraphMutationSpec) -> tuple[Mapping[str, Any], ...]:
    config = spec.config if isinstance(spec.config, Mapping) else {}
    sources = config.get("context_sources")
    if isinstance(sources, Sequence) and not isinstance(
        sources, (str, bytes, bytearray)
    ):
        explicit_sources = tuple(item for item in sources if isinstance(item, Mapping))
        if explicit_sources:
            return explicit_sources
    contract = _as_mapping(config.get("context_contract")) or {}
    fallback_sources: list[Mapping[str, Any]] = []
    history_input = contract.get("history_input")
    if history_input is not None:
        fallback_sources.append(
            {"kind": "conversation_history", "source": history_input}
        )
    current_prompt_input = contract.get("current_prompt_input")
    if current_prompt_input is not None:
        fallback_sources.append(
            {"kind": "latest_user_prompt", "source": current_prompt_input}
        )
    return tuple(fallback_sources)


def _resolve_prepared_context_source(
    source: Mapping[str, Any],
    *,
    prompt: str,
    session_messages: Sequence[OpenAIMessage],
    resolve_source: Callable[[str | None], Any] | None,
) -> Any:
    binding = source.get("source")
    if binding in {"state.chat_history", "state.session_messages"}:
        return session_messages
    if binding == "prompt":
        return prompt
    if resolve_source is not None:
        return resolve_source(str(binding) if binding is not None else None)
    return None


def _stringify_prepared_context_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, OpenAIMessage):
        return f"{value.role}: {value.content}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rendered = [_stringify_prepared_context_value(item) for item in value]
        return "\n".join(part for part in rendered if part)
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True)
    return str(value)
