"""Run the authorized MLX competency gate for the sealed MLE8 package."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import resource
import struct
import time
from pathlib import Path
from typing import Any

from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.mlx_local_embedding import (
    MLXLocalEmbeddingConfig,
    MLXPreparedEmbeddingArtifacts,
    create_mlx_local_embedding_adapter,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    derive_embedding_execution_binding,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    CoverageReport,
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
    IndexBundleManifest,
    SnapshotDocument,
    validate_index_artifacts,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    ROBERTA_ENCODER_MLX_V1_ABI,
    RobertaEncoderMlxV1DescriptorValidator,
    RobertaEncoderMlxV1EmbeddingBackend,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    derive_model_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_ROOT = Path(__file__).parents[2]
_PACKAGE = _ROOT / "tests" / "fixtures" / "mlx-all-distilroberta-v1" / "mle8-package"


def main() -> int:
    """Run one local-only package-bound MLX embedding/index competency check."""

    arguments = _arguments()
    model_root = arguments.model_root.resolve()
    lock, descriptor, requirements = _load_package()
    _validate_sources(model_root, lock)
    prepared_weights = arguments.prepared_weights.resolve()
    _validate_prepared_weights(prepared_weights, lock)
    documents = _documents()
    fixture = _fixture()
    _validate_fixture(descriptor, fixture)
    materials = MLXPreparedEmbeddingArtifacts(
        execution_abi_id=ROBERTA_ENCODER_MLX_V1_ABI.abi_id,
        execution_abi_version=ROBERTA_ENCODER_MLX_V1_ABI.version,
        execution_abi_contract_digest=ROBERTA_ENCODER_MLX_V1_ABI.contract_digest,
        execution_descriptor_digest=descriptor.digest,
        material_lock_digest=lock.digest,
        execution_descriptor=descriptor,
    )
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = create_mlx_local_embedding_adapter(
        MLXLocalEmbeddingConfig(
            material_resolver=lambda: materials,
            descriptor_validators=ExecutionDescriptorValidatorRegistry(
                (RobertaEncoderMlxV1DescriptorValidator(),)
            ),
        ),
        backend=RobertaEncoderMlxV1EmbeddingBackend(
            artifact_reader=lambda role: (
                prepared_weights.read_bytes()
                if role == "weights"
                else (model_root / _source_filename(lock, role)).read_bytes()
            )
        ),
    ).embed(tuple(EmbeddingInputItem(item["id"], item["text"]) for item in documents))
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_error = _validate_vectors(result, fixture, descriptor)
    binding = derive_embedding_execution_binding(
        model_binding=derive_model_execution_binding(
            lock=lock,
            requirements=requirements,
            execution_descriptor=descriptor,
            descriptor_validators=ExecutionDescriptorValidatorRegistry(
                (RobertaEncoderMlxV1DescriptorValidator(),)
            ),
        ),
        requirements=requirements,
    )
    _validate_opaque_index(binding, documents)
    items = result.items
    receipt = {
        "descriptor_digest": descriptor.digest,
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "fixture_digest": hashlib.sha256(
            (_PACKAGE / "conformance-fixture.json").read_bytes()
        ).hexdigest(),
        "format_version": 1,
        "limits": descriptor.abi_fields["limits"],
        "material_lock_digest": lock.digest,
        "max_abs_error": max_error,
        "max_rss_bytes": max(before, after),
        "mlx_version": _mlx_version(),
        "opaque_output_ids": ["index-bundle-1", "coverage-report-1"],
        "package_id": lock.logical_model_id,
        "status": "passed",
        "vector_count": len(items),
        "vector_dimension": len(items[0].vector),
    }
    arguments.receipt.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--prepared-weights", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _load_package():
    lock = parse_model_dependency_lock(_load_json("model-materials.json"))
    descriptor = parse_execution_descriptor(_load_json("execution-descriptor.json"))
    from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements

    requirements = CapabilityRequirements.from_mapping(
        _load_json("capability-requirements.json")
    )
    return lock, descriptor, requirements


def _load_json(name: str) -> dict[str, Any]:
    value = json.loads((_PACKAGE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("package evidence is invalid")
    return value


def _validate_sources(model_root: Path, lock: object) -> None:
    for source in getattr(lock, "sources", ()):
        path = model_root / source.filename
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256
        ):
            raise RuntimeError("locked material is unavailable")


def _validate_prepared_weights(path: Path, lock: object) -> None:
    operations = getattr(lock, "preparation", ())
    if len(operations) != 1 or not path.is_file():
        raise RuntimeError("locked prepared material is unavailable")
    output = operations[0].output
    if (
        output.role != "weights"
        or hashlib.sha256(path.read_bytes()).hexdigest() != output.sha256
    ):
        raise RuntimeError("locked prepared material is unavailable")


def _documents() -> list[dict[str, str]]:
    value = _load_json("synthetic-documents.json")
    documents = value.get("documents")
    if (
        value.get("format_version") != 1
        or not isinstance(documents, list)
        or not all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("text"), str)
            for item in documents
        )
    ):
        raise RuntimeError("synthetic documents are invalid")
    return documents


def _fixture() -> dict[str, Any]:
    return _load_json("conformance-fixture.json")


def _validate_fixture(descriptor: object, fixture: dict[str, Any]) -> None:
    conformance = getattr(descriptor, "abi_fields", {}).get("conformance")
    if (
        not isinstance(conformance, dict)
        or conformance.get("fixture_sha256")
        != hashlib.sha256(
            (_PACKAGE / "conformance-fixture.json").read_bytes()
        ).hexdigest()
        or not isinstance(fixture.get("expected_vectors"), list)
    ):
        raise RuntimeError("conformance fixture is invalid")


def _source_filename(lock: object, role: str) -> str:
    for source in getattr(lock, "sources", ()):
        if source.role == role:
            return source.filename
    raise RuntimeError("locked material is unavailable")


def _validate_vectors(
    result: object, fixture: dict[str, Any], descriptor: object
) -> float:
    expected = fixture["expected_vectors"]
    items = getattr(result, "items", ())
    conformance = getattr(descriptor, "abi_fields", {}).get("conformance")
    if (
        not isinstance(expected, list)
        or not isinstance(conformance, dict)
        or len(items) != len(expected)
    ):
        raise RuntimeError("MLX conformance result is invalid")
    maximum = 0.0
    for actual, reference in zip(items, expected, strict=True):
        vector = base64.b64decode(reference["vector_f32le_base64"])
        values = struct.unpack(f"<{len(actual.vector)}f", vector)
        if actual.id != reference["id"] or len(actual.vector) != len(values):
            raise RuntimeError("MLX conformance result is invalid")
        maximum = max(
            maximum,
            *(
                abs(value - expected_value)
                for value, expected_value in zip(actual.vector, values, strict=True)
            ),
        )
    if maximum > conformance["max_error"]:
        raise RuntimeError("MLX conformance tolerance exceeded")
    return maximum


def _validate_opaque_index(binding: object, documents: list[dict[str, str]]) -> None:
    snapshot = DocumentSnapshot.create(
        tuple(
            SnapshotDocument(item["id"], "text/plain", item["text"].encode("utf-8"))
            for item in sorted(documents, key=lambda item: item["id"])
        ),
        policy=DocumentSnapshotPolicy(16, 65536, 1048576, ("text/plain",)),
    )
    index_binding = IndexArtifactBinding(
        binding.material_lock_digest,
        binding.capability_contract_digest,
        "a" * 64,
    )
    bundle = b"opaque-index-bundle"
    manifest = IndexBundleManifest.create(
        bundle=bundle,
        snapshot=snapshot,
        binding=index_binding,
        document_count=len(documents),
        chunk_count=len(documents),
        indexed_count=len(documents),
        skipped_count=0,
        deleted_count=0,
        error_count=0,
    )
    report = CoverageReport.create(
        snapshot=snapshot,
        binding=index_binding,
        prior_bundle_digest=None,
        document_count=len(documents),
        chunk_count=len(documents),
        indexed_count=len(documents),
        skipped_count=0,
        deleted_count=0,
        error_count=0,
        error_classifications=(),
    )
    validate_index_artifacts(
        bundle=bundle,
        manifest=manifest,
        report=report,
        snapshot=snapshot,
        binding=index_binding,
        max_bundle_bytes=64,
        max_report_bytes=2048,
    )


def _mlx_version() -> str:
    import mlx.core as mx

    return mx.__version__


if __name__ == "__main__":
    raise SystemExit(main())
