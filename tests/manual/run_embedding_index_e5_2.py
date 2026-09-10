"""Run the explicitly authorized E5.2 embedding-index acceptance fixture.

This is a manual harness, never a pytest or CI workload. Its JSON evidence has
only immutable identities and aggregate counts; the caller selects where that
evidence is retained.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from hashlib import sha256
from pathlib import Path

from dynamic_agent_runner.local_models import (
    HuggingFaceModelFileReference,
    LlamaCppLocalEmbeddingAdapter,
    LlamaCppLocalEmbeddingConfig,
    LocalModelPathConfig,
    resolve_local_model_path,
)
from dynamic_agent_runner.workflow_host.capabilities import CapabilityContract
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingExecutionService,
    EmbeddingProviderCatalog,
    EmbeddingTextItem,
    LocalEmbeddingAdapterProvider,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
    SnapshotDocument,
)
from dynamic_agent_runner.workflow_host.embedding_index_builder import (
    ExperimentalBuilderBinding,
    ExperimentalBuilderCatalog,
    IndexBuilderDescriptor,
    OwnerAuthorizedBuilderProfile,
    run_owner_authorized_builder,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    DeclaredResultArtifact,
)


_ROOT = Path(__file__).parents[2]
_FIXTURE = _ROOT / "tests/fixtures/embedding-index-e5-2"
_TOY_BUILDER = _ROOT / "tests/fixtures/embedding-index-toy-builder/toy_builder.py"
_LIMITS = EmbeddingBatchLimits(4, 4096, 8192, 1024, 4)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manual fixture is invalid")
    return value


def _load_toy_builder() -> object:
    spec = importlib.util.spec_from_file_location("e5_2_toy_builder", _TOY_BUILDER)
    if spec is None or spec.loader is None:
        raise ValueError("manual builder fixture is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ToyIndexBuilder()


def _snapshot(path: Path) -> DocumentSnapshot:
    value = _load_json(path)
    documents = value.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manual snapshot is invalid")
    parsed: list[SnapshotDocument] = []
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("manual snapshot is invalid")
        identifier = document.get("document_id")
        media_type = document.get("media_type")
        content = document.get("content")
        if not all(
            isinstance(value, str) for value in (identifier, media_type, content)
        ):
            raise ValueError("manual snapshot is invalid")
        parsed.append(SnapshotDocument(identifier, media_type, content.encode("utf-8")))
    total_bytes = sum(len(document.content) for document in parsed)
    return DocumentSnapshot.create(
        tuple(parsed),
        policy=DocumentSnapshotPolicy(
            max_documents=len(parsed),
            max_document_bytes=max(len(document.content) for document in parsed),
            max_snapshot_bytes=total_bytes,
            accepted_media_types=("text/plain",),
        ),
    )


def _material_adapter(material: dict[str, object]) -> tuple[object, str]:
    required = ("repository", "revision", "filename", "sha256")
    if not all(isinstance(material.get(key), str) for key in required):
        raise ValueError("manual material fixture is invalid")
    reference = HuggingFaceModelFileReference(
        repo_id=material["repository"],
        revision=material["revision"],
        filename=material["filename"],
    )
    resolved = resolve_local_model_path(
        LocalModelPathConfig(
            model_filename=material["filename"],
            explicit_model_path=_FIXTURE / "missing-model",
            huggingface_file=reference,
        ),
    )
    if _sha256(resolved) != material["sha256"]:
        raise ValueError("manual material digest does not match")
    return (
        LlamaCppLocalEmbeddingAdapter(
            LlamaCppLocalEmbeddingConfig(
                model_path=resolved,
                expected_model_id=material["filename"],
                allow_network=False,
            )
        ),
        sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def run(*, snapshot_path: Path) -> dict[str, object]:
    """Execute one fixture run and return a redacted acceptance receipt."""

    material = _load_json(_FIXTURE / "model-material.json")
    adapter, material_digest = _material_adapter(material)
    contract = CapabilityContract(
        "embedding.execute.v1",
        "1",
        sha256(b"embedding.execute.v1:deterministic").hexdigest(),
        ("deterministic",),
    )
    model_binding = ModelExecutionBinding(
        logical_model_id="manual-embedding-material",
        runner_contract_id="llama-cpp-v1",
        runner_contract_version="1",
        loader_profile_contract_id="llama-cpp-embedding-v1",
        loader_profile_contract_version="1",
        material_lock_digest=material_digest,
        capability_requirements_digest=contract.contract_digest,
        runner_capability_id="model.execution.llama-cpp.v1",
        runner_capability_version="1",
        runner_capability_digest=contract.contract_digest,
    )
    binding = EmbeddingExecutionBinding(
        model_binding,
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
    )
    service = EmbeddingExecutionService(
        providers=EmbeddingProviderCatalog(
            (
                LocalEmbeddingAdapterProvider(
                    "manual-local-llama-cpp", contract, adapter
                ),
            )
        ),
        host_limits=_LIMITS,
    )
    asset_digest = _sha256(_TOY_BUILDER)
    package_digest = sha256(("e5.2-toy-package:" + asset_digest).encode()).hexdigest()
    descriptor = IndexBuilderDescriptor(
        package_digest=package_digest,
        asset_digest=asset_digest,
        result_artifacts=(
            DeclaredResultArtifact("coverage_report", 4096),
            DeclaredResultArtifact("index_bundle", 65536),
            DeclaredResultArtifact("index_manifest", 4096),
        ),
        max_prior_bundle_bytes=65536,
    )
    snapshot = _snapshot(snapshot_path)

    def embed(items: tuple[EmbeddingTextItem, ...]):
        return service.execute(
            binding=binding,
            selected_provider_ids=("manual-local-llama-cpp",),
            package_limits=_LIMITS,
            items=items,
        )

    result = run_owner_authorized_builder(
        profile=OwnerAuthorizedBuilderProfile(package_digest, asset_digest),
        descriptor=descriptor,
        catalog=ExperimentalBuilderCatalog(
            (ExperimentalBuilderBinding(asset_digest, _load_toy_builder()),)
        ),
        snapshot=snapshot,
        prior_bundle=None,
        binding=IndexArtifactBinding(
            material_digest, contract.contract_digest, descriptor.digest
        ),
        embed=embed,
    )
    report = json.loads(result.read("coverage_report"))
    forbidden = {"document_id", "path", "content", "text", "vector", "bundle"}
    if forbidden.intersection(report):
        raise ValueError("manual coverage report is not aggregate-only")
    return {
        "bundle_digest": sha256(result.read("index_bundle")).hexdigest(),
        "coverage_report_digest": sha256(result.read("coverage_report")).hexdigest(),
        "embedding_capability_contract_digest": contract.contract_digest,
        "embedding_material_lock_digest": material_digest,
        "index_builder_digest": descriptor.digest,
        "package_digest": package_digest,
        "counts": {
            key: report[key]
            for key in (
                "document_count",
                "chunk_count",
                "indexed_count",
                "skipped_count",
                "deleted_count",
                "error_count",
            )
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=_FIXTURE / "snapshot.json")
    parser.add_argument("--evidence", type=Path, required=True)
    arguments = parser.parse_args()
    evidence = run(snapshot_path=arguments.snapshot)
    arguments.evidence.parent.mkdir(parents=True, exist_ok=True)
    arguments.evidence.write_text(
        json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
