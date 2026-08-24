"""Tests for the immutable DAR authoring package catalog."""

from __future__ import annotations

import shutil
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host.catalog import PackageCatalog  # noqa: E402
from dynamic_agent_runner.workflow_host.package_signatures import sign_manifest  # noqa: E402
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)  # noqa: E402
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager  # noqa: E402
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _stage(tmp_path: Path, content: str | None = None):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    if content is not None:
        (source / "agent-design.md").write_text(content, encoding="utf-8")
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        source_handle, now=NOW
    )


def _stage_publisher_signed(tmp_path: Path):
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    digest = hashlib.sha256()
    files = []
    for path in sorted(source.iterdir()):
        body = path.read_bytes()
        file_digest = hashlib.sha256(body).hexdigest()
        digest.update(f"{path.name}\0{file_digest}\0{len(body)}\n".encode("utf-8"))
        files.append(
            {"byte_count": len(body), "path": path.name, "sha256": file_digest}
        )
    manifest = json.dumps(
        {
            "content_digest": digest.hexdigest(),
            "dar_runtime": {
                "distribution": "dynamic-agent-runner",
                "required_version": "0.1.16",
            },
            "descriptor_format_version": 1,
            "files": files,
            "format_version": 2,
            "package_id": "dar-authoring-no-tool-template",
            "runtime_format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (source / "package-manifest.json").write_bytes(manifest)
    key_id = "publisher.example.v1"
    private_key = Ed25519PrivateKey.generate()
    signature = sign_manifest(
        manifest=manifest, key_id=key_id, private_key=private_key.private_bytes_raw()
    )
    (source / "package-signature.json").write_text(
        json.dumps(signature, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    store = PrivateStateStore(tmp_path / "state")
    source_handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_publisher_zip(archive, now=NOW)
    return PrivatePackageStager(
        store=store,
        private_root=tmp_path / "staging",
        trusted_keys=lambda: {key_id: private_key.public_key().public_bytes_raw()},
    ).stage(source_handle, now=NOW)


def test_catalog_reimport_is_idempotent(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    catalog = PackageCatalog(tmp_path / "catalog")

    first = catalog.import_staged(staged)
    second = catalog.import_staged(staged)

    assert first == second
    assert catalog.revisions("dar-authoring-no-tool-template") == (first,)
    assert first.package_id == "dar-authoring-no-tool-template"
    assert first.revision_digest == staged.digest
    assert first.package_root == staged.root
    assert first.trust == "human_selected_local"


def test_catalog_retains_prior_revisions_for_same_package_id(tmp_path: Path) -> None:
    first_staged = _stage(tmp_path / "one", content="first revision")
    second_staged = _stage(tmp_path / "two", content="second revision")
    catalog = PackageCatalog(tmp_path / "catalog")

    first = catalog.import_staged(first_staged)
    second = catalog.import_staged(second_staged)

    revisions = catalog.revisions("dar-authoring-no-tool-template")
    assert {revision.revision_digest for revision in revisions} == {
        first.revision_digest,
        second.revision_digest,
    }
    assert len(revisions) == 2


def test_catalog_revisions_survive_reopen(tmp_path: Path) -> None:
    staged = _stage(tmp_path)
    root = tmp_path / "catalog"
    PackageCatalog(root).import_staged(staged)

    revisions = PackageCatalog(root).revisions("dar-authoring-no-tool-template")

    assert len(revisions) == 1
    assert revisions[0].revision_digest == staged.digest


def test_catalog_retains_verified_publisher_provenance(tmp_path: Path) -> None:
    staged = _stage_publisher_signed(tmp_path)
    catalog = PackageCatalog(tmp_path / "catalog")

    revision = catalog.import_staged(staged)
    reopened = PackageCatalog(tmp_path / "catalog").revision(
        revision.package_id, revision.revision_digest
    )

    assert revision.trust == "publisher_signature"
    assert revision.publisher_key_id == "publisher.example.v1"
    assert reopened == revision
