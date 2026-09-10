"""Workflow-local fixture asset with toy document and index semantics."""

from __future__ import annotations

import json
from hashlib import sha256

from dynamic_agent_runner.workflow_host.embedding_execution import EmbeddingTextItem
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    CoverageReport,
    IndexBundleManifest,
)


class ToyIndexBuilder:
    """Build a deterministic JSON index used only by the embedding fixture."""

    def run(self, *, snapshot, prior_bundle, binding, embed, results) -> None:
        items = tuple(
            EmbeddingTextItem(document.document_id, document.content.decode("utf-8"))
            for document in snapshot.documents
        )
        vectors = embed(items)
        bundle = json.dumps(
            {
                "entries": [
                    {"id": vector.item_id, "vector": list(vector.values)}
                    for vector in vectors
                ]
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest = IndexBundleManifest.create(
            bundle=bundle,
            snapshot=snapshot,
            binding=binding,
            document_count=len(items),
            chunk_count=len(items),
            indexed_count=len(items),
            skipped_count=0,
            deleted_count=0,
            error_count=0,
        )
        report = CoverageReport.create(
            snapshot=snapshot,
            binding=binding,
            prior_bundle_digest=(
                sha256(prior_bundle).hexdigest() if prior_bundle is not None else None
            ),
            document_count=len(items),
            chunk_count=len(items),
            indexed_count=len(items),
            skipped_count=0,
            deleted_count=0,
            error_count=0,
            error_classifications=(),
        )
        results.write("coverage_report", report.canonical_bytes)
        results.write("index_bundle", bundle)
        results.write("index_manifest", manifest.canonical_bytes)
