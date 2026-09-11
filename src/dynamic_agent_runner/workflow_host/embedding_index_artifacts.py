"""Sealed document-snapshot ingress and opaque embedding-index egress models."""

from __future__ import annotations

import json
import re
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Mapping, Sequence


_DOCUMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ERROR_CLASSIFICATION = re.compile(r"[a-z][a-z0-9_]{0,63}")


class DocumentSnapshotError(ValueError):
    """Raised when a document snapshot is outside its sealed policy."""


class IndexArtifactError(ValueError):
    """Raised when opaque index artifacts do not match their sealed binding."""


@dataclass(frozen=True)
class DocumentSnapshotPolicy:
    """Bounded, workflow-declared constraints for one document snapshot."""

    max_documents: int
    max_document_bytes: int
    max_snapshot_bytes: int
    accepted_media_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(
            not _positive(value)
            for value in (
                self.max_documents,
                self.max_document_bytes,
                self.max_snapshot_bytes,
            )
        ):
            raise DocumentSnapshotError("document snapshot policy is invalid")
        if not self.accepted_media_types or any(
            not isinstance(value, str) or not value
            for value in self.accepted_media_types
        ):
            raise DocumentSnapshotError("document snapshot policy is invalid")


@dataclass(frozen=True)
class SnapshotDocument:
    """One private document record supplied by a host-controlled snapshot."""

    document_id: str
    media_type: str
    content: bytes = field(repr=False)

    @property
    def content_hash(self) -> str:
        """Return the immutable content identity without exposing content."""

        return sha256(self.content).hexdigest()


@dataclass(frozen=True)
class DocumentSnapshot:
    """A canonically ordered, bounded set of private document bytes."""

    documents: tuple[SnapshotDocument, ...]
    snapshot_digest: str

    @classmethod
    def create(
        cls,
        documents: Sequence[SnapshotDocument],
        *,
        policy: DocumentSnapshotPolicy,
    ) -> "DocumentSnapshot":
        """Validate and seal a caller-provided document set."""

        normalized = tuple(documents)
        _validate_documents(normalized, policy)
        return cls(normalized, sha256(_snapshot_manifest_bytes(normalized)).hexdigest())

    @classmethod
    def from_wire_bytes(
        cls, content: bytes, *, policy: DocumentSnapshotPolicy
    ) -> "DocumentSnapshot":
        """Decode exactly one canonical sealed snapshot wire representation."""

        if not isinstance(content, bytes) or content.startswith(b"\xef\xbb\xbf"):
            raise DocumentSnapshotError("document snapshot is invalid")
        try:
            value = json.loads(
                content.decode("utf-8"), object_pairs_hook=_no_duplicate_object
            )
            if (
                not isinstance(value, dict)
                or _canonical_json(value) != content
                or set(value) != {"format_version", "documents"}
                or value["format_version"] != 1
                or not isinstance(value["documents"], list)
            ):
                raise ValueError
            documents = tuple(_wire_document(item) for item in value["documents"])
            return cls.create(documents, policy=policy)
        except (
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise DocumentSnapshotError("document snapshot is invalid") from error

    @property
    def manifest_bytes(self) -> bytes:
        """Return canonical private manifest bytes without document content."""

        return _snapshot_manifest_bytes(self.documents)

    @property
    def wire_bytes(self) -> bytes:
        """Return the canonical sealed input encoding, including private bytes."""

        return _canonical_json(
            {
                "format_version": 1,
                "documents": [
                    {
                        "content_base64": b64encode(document.content).decode("ascii"),
                        "document_id": document.document_id,
                        "media_type": document.media_type,
                    }
                    for document in self.documents
                ],
            }
        )


@dataclass(frozen=True)
class IndexArtifactBinding:
    """Exact sealed identities required for one index artifact result."""

    embedding_material_lock_digest: str
    embedding_capability_contract_digest: str
    index_builder_digest: str

    def __post_init__(self) -> None:
        if any(
            not _DIGEST.fullmatch(value)
            for value in (
                self.embedding_material_lock_digest,
                self.embedding_capability_contract_digest,
                self.index_builder_digest,
            )
        ):
            raise IndexArtifactError("index artifact binding is invalid")

    def to_mapping(self) -> dict[str, str]:
        """Return the canonical binding fields shared by result manifests."""

        return {
            "embedding_material_lock_digest": self.embedding_material_lock_digest,
            "embedding_capability_contract_digest": self.embedding_capability_contract_digest,
            "index_builder_digest": self.index_builder_digest,
        }


@dataclass(frozen=True)
class IndexBundleManifest:
    """Generic metadata bound to one opaque index-bundle byte sequence."""

    snapshot_digest: str
    binding: IndexArtifactBinding
    bundle_sha256: str
    document_count: int
    chunk_count: int
    indexed_count: int
    skipped_count: int
    deleted_count: int
    error_count: int

    @classmethod
    def create(
        cls,
        *,
        bundle: bytes,
        snapshot: DocumentSnapshot,
        binding: IndexArtifactBinding,
        document_count: int,
        chunk_count: int,
        indexed_count: int,
        skipped_count: int,
        deleted_count: int,
        error_count: int,
    ) -> "IndexBundleManifest":
        """Create one manifest after validating only generic aggregate metadata."""

        if not isinstance(bundle, bytes):
            raise IndexArtifactError("index bundle is invalid")
        manifest = cls(
            snapshot.snapshot_digest,
            binding,
            sha256(bundle).hexdigest(),
            document_count,
            chunk_count,
            indexed_count,
            skipped_count,
            deleted_count,
            error_count,
        )
        manifest._validate()
        return manifest

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "IndexBundleManifest":
        """Parse only the exact generic bundle-manifest shape."""

        expected = {
            "format_version",
            "snapshot_digest",
            "embedding_material_lock_digest",
            "embedding_capability_contract_digest",
            "index_builder_digest",
            "bundle_sha256",
            "document_count",
            "chunk_count",
            "indexed_count",
            "skipped_count",
            "deleted_count",
            "error_count",
        }
        if set(value) != expected or value.get("format_version") != 1:
            raise IndexArtifactError("index bundle manifest is invalid")
        try:
            manifest = cls(
                _string(value["snapshot_digest"]),
                IndexArtifactBinding(
                    _string(value["embedding_material_lock_digest"]),
                    _string(value["embedding_capability_contract_digest"]),
                    _string(value["index_builder_digest"]),
                ),
                _string(value["bundle_sha256"]),
                _integer(value["document_count"]),
                _integer(value["chunk_count"]),
                _integer(value["indexed_count"]),
                _integer(value["skipped_count"]),
                _integer(value["deleted_count"]),
                _integer(value["error_count"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IndexArtifactError("index bundle manifest is invalid") from error
        manifest._validate()
        return manifest

    def _validate(self) -> None:
        if (
            not _DIGEST.fullmatch(self.snapshot_digest)
            or not _DIGEST.fullmatch(self.bundle_sha256)
            or any(
                not _nonnegative(value)
                for value in (
                    self.document_count,
                    self.chunk_count,
                    self.indexed_count,
                    self.skipped_count,
                    self.deleted_count,
                    self.error_count,
                )
            )
        ):
            raise IndexArtifactError("index bundle manifest is invalid")

    @property
    def canonical_bytes(self) -> bytes:
        """Return canonical bytes for storage or a host-owned result receipt."""

        return _canonical_json(
            {
                "format_version": 1,
                "snapshot_digest": self.snapshot_digest,
                **self.binding.to_mapping(),
                "bundle_sha256": self.bundle_sha256,
                **_counts(self),
            }
        )


@dataclass(frozen=True)
class CoverageReport:
    """Aggregate-only report that cannot carry document or vector content."""

    snapshot_digest: str
    binding: IndexArtifactBinding
    prior_bundle_digest: str | None
    document_count: int
    chunk_count: int
    indexed_count: int
    skipped_count: int
    deleted_count: int
    error_count: int
    error_classifications: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        snapshot: DocumentSnapshot,
        binding: IndexArtifactBinding,
        prior_bundle_digest: str | None,
        document_count: int,
        chunk_count: int,
        indexed_count: int,
        skipped_count: int,
        deleted_count: int,
        error_count: int,
        error_classifications: Sequence[str],
    ) -> "CoverageReport":
        """Create an aggregate-only report bound to one snapshot and provider."""

        report = cls(
            snapshot.snapshot_digest,
            binding,
            prior_bundle_digest,
            document_count,
            chunk_count,
            indexed_count,
            skipped_count,
            deleted_count,
            error_count,
            tuple(error_classifications),
        )
        report._validate()
        return report

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "CoverageReport":
        """Parse only the exact generic report shape, rejecting extra content."""

        expected = {
            "format_version",
            "snapshot_digest",
            "embedding_material_lock_digest",
            "embedding_capability_contract_digest",
            "index_builder_digest",
            "prior_bundle_digest",
            "document_count",
            "chunk_count",
            "indexed_count",
            "skipped_count",
            "deleted_count",
            "error_count",
            "error_classifications",
        }
        if set(value) != expected or value.get("format_version") != 1:
            raise IndexArtifactError("coverage report is invalid")
        try:
            binding = IndexArtifactBinding(
                _string(value["embedding_material_lock_digest"]),
                _string(value["embedding_capability_contract_digest"]),
                _string(value["index_builder_digest"]),
            )
            raw_classifications = value["error_classifications"]
            if not isinstance(raw_classifications, (list, tuple)):
                raise ValueError("error classifications are invalid")
            classifications = tuple(_string(item) for item in raw_classifications)
            report = cls(
                _string(value["snapshot_digest"]),
                binding,
                value["prior_bundle_digest"],
                _integer(value["document_count"]),
                _integer(value["chunk_count"]),
                _integer(value["indexed_count"]),
                _integer(value["skipped_count"]),
                _integer(value["deleted_count"]),
                _integer(value["error_count"]),
                classifications,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IndexArtifactError("coverage report is invalid") from error
        report._validate()
        return report

    def _validate(self) -> None:
        if (
            not _DIGEST.fullmatch(self.snapshot_digest)
            or self.prior_bundle_digest is not None
            and not _DIGEST.fullmatch(self.prior_bundle_digest)
            or any(
                not _nonnegative(value)
                for value in (
                    self.document_count,
                    self.chunk_count,
                    self.indexed_count,
                    self.skipped_count,
                    self.deleted_count,
                    self.error_count,
                )
            )
            or len(set(self.error_classifications)) != len(self.error_classifications)
            or any(
                not isinstance(value, str) or not _ERROR_CLASSIFICATION.fullmatch(value)
                for value in self.error_classifications
            )
        ):
            raise IndexArtifactError("coverage report is invalid")

    @property
    def canonical_bytes(self) -> bytes:
        """Return the only serializable aggregate report representation."""

        return _canonical_json(
            {
                "format_version": 1,
                "snapshot_digest": self.snapshot_digest,
                **self.binding.to_mapping(),
                "prior_bundle_digest": self.prior_bundle_digest,
                **_counts(self),
                "error_classifications": list(self.error_classifications),
            }
        )


@dataclass(frozen=True)
class IndexArtifactResult:
    """Public opaque receipt for validated bundle and report artifacts."""

    bundle_sha256: str
    bundle_byte_count: int
    report_sha256: str
    report_byte_count: int


def validate_index_artifacts(
    *,
    bundle: bytes,
    manifest: IndexBundleManifest,
    report: CoverageReport,
    snapshot: DocumentSnapshot,
    binding: IndexArtifactBinding,
    max_bundle_bytes: int,
    max_report_bytes: int,
) -> IndexArtifactResult:
    """Validate opaque egress against the exact snapshot and provider binding."""

    if (
        not isinstance(bundle, bytes)
        or not _positive(max_bundle_bytes)
        or not _positive(max_report_bytes)
        or len(bundle) > max_bundle_bytes
    ):
        raise IndexArtifactError("index bundle is invalid")
    manifest._validate()
    report._validate()
    if manifest.bundle_sha256 != sha256(bundle).hexdigest():
        raise IndexArtifactError("index bundle is invalid")
    if (
        manifest.snapshot_digest != snapshot.snapshot_digest
        or report.snapshot_digest != snapshot.snapshot_digest
        or manifest.binding != binding
        or report.binding != binding
    ):
        raise IndexArtifactError("index artifact binding is invalid")
    report_bytes = report.canonical_bytes
    if len(report_bytes) > max_report_bytes:
        raise IndexArtifactError("coverage report is invalid")
    return IndexArtifactResult(
        manifest.bundle_sha256,
        len(bundle),
        sha256(report_bytes).hexdigest(),
        len(report_bytes),
    )


def _validate_documents(
    documents: tuple[SnapshotDocument, ...], policy: DocumentSnapshotPolicy
) -> None:
    if not documents or len(documents) > policy.max_documents:
        raise DocumentSnapshotError("document snapshot is invalid")
    identifiers = tuple(document.document_id for document in documents)
    if identifiers != tuple(sorted(identifiers)):
        raise DocumentSnapshotError("document snapshot order is invalid")
    if len(set(identifiers)) != len(identifiers):
        raise DocumentSnapshotError("document identifiers must be unique")
    total = 0
    for document in documents:
        if (
            not isinstance(document.document_id, str)
            or not _DOCUMENT_ID.fullmatch(document.document_id)
            or document.media_type not in policy.accepted_media_types
            or not isinstance(document.content, bytes)
            or len(document.content) > policy.max_document_bytes
        ):
            raise DocumentSnapshotError("document snapshot is invalid")
        total += len(document.content)
    if total > policy.max_snapshot_bytes:
        raise DocumentSnapshotError("document snapshot is invalid")


def _wire_document(value: object) -> SnapshotDocument:
    if not isinstance(value, dict) or set(value) != {
        "content_base64",
        "document_id",
        "media_type",
    }:
        raise ValueError
    encoded = value["content_base64"]
    if (
        not isinstance(encoded, str)
        or not isinstance(value["document_id"], str)
        or not isinstance(value["media_type"], str)
    ):
        raise ValueError
    content = b64decode(encoded.encode("ascii"), validate=True)
    if b64encode(content).decode("ascii") != encoded:
        raise ValueError
    return SnapshotDocument(value["document_id"], value["media_type"], content)


def _snapshot_manifest_bytes(documents: tuple[SnapshotDocument, ...]) -> bytes:
    return _canonical_json(
        {
            "format_version": 1,
            "documents": [
                {
                    "document_id": document.document_id,
                    "media_type": document.media_type,
                    "byte_count": len(document.content),
                    "content_hash": document.content_hash,
                }
                for document in documents
            ],
        }
    )


def _counts(value: object) -> dict[str, int]:
    return {
        name: getattr(value, name)
        for name in (
            "document_count",
            "chunk_count",
            "indexed_count",
            "skipped_count",
            "deleted_count",
            "error_count",
        )
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError
    return value


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("string is invalid")
    return value


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("integer is invalid")
    return value
