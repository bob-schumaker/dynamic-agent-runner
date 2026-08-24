"""Tests for private no-follow staging of selected DAR packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.package_sources import PackageSourceSelectionPolicy  # noqa: E402
from dar_workflow_server.package_signatures import sign_manifest  # noqa: E402
from dar_workflow_server.staging import (  # noqa: E402
    PackageStagingError,
    PrivatePackageStager,
)
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _selection(tmp_path: Path, source: Path) -> tuple[str, PrivateStateStore]:
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    return handle, store


def _source_package(tmp_path: Path) -> Path:
    source = tmp_path / "packages" / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    return source


def _write_source_manifest(source: Path) -> bytes:
    entries = []
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*")):
        relative_path = path.relative_to(source).as_posix()
        if not path.is_file() or relative_path in {
            "package-manifest.json",
            "package-signature.json",
        }:
            continue
        body = path.read_bytes()
        body_digest = hashlib.sha256(body).hexdigest()
        digest.update(f"{relative_path}\0{body_digest}\0{len(body)}\n".encode("utf-8"))
        entries.append(
            {
                "byte_count": len(body),
                "path": relative_path,
                "sha256": body_digest,
            }
        )
    value = json.dumps(
        {
            "content_digest": digest.hexdigest(),
            "files": entries,
            "format_version": 1,
            "package_id": "dar-authoring-no-tool-template",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (source / "package-manifest.json").write_bytes(value)
    return value


def _archive_package(tmp_path: Path) -> Path:
    source = _source_package(tmp_path)
    _write_source_manifest(source)
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    return archive


def _archive_selection(tmp_path: Path, archive: Path) -> tuple[str, PrivateStateStore]:
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_zip(archive, now=NOW)
    return handle, store


def _signed_archive(tmp_path: Path, *, key_id: str, private_key: bytes) -> Path:
    source = _source_package(tmp_path)
    manifest = _write_source_manifest(source)
    signature = sign_manifest(manifest=manifest, key_id=key_id, private_key=private_key)
    (source / "package-signature.json").write_text(
        json.dumps(signature, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    return archive


def test_staging_copies_selected_package_and_validates_dar(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    handle, store = _selection(tmp_path, source)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    assert staged.root.is_dir()
    assert staged.root != source
    assert staged.file_count == 4
    assert staged.byte_count > 0
    assert len(staged.digest) == 64
    assert (staged.root / "agent-runtime.yaml").read_text(encoding="utf-8") == (
        source / "agent-runtime.yaml"
    ).read_text(encoding="utf-8")


def test_staging_writes_a_canonical_content_manifest(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    handle, store = _selection(tmp_path, source)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    manifest = json.loads(
        (staged.root / "package-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["format_version"] == 1
    assert manifest["package_id"] == "dar-authoring-no-tool-template"
    assert manifest["content_digest"] == staged.digest
    assert manifest["files"] == [
        {
            "byte_count": len((source / path).read_bytes()),
            "path": path,
            "sha256": hashlib.sha256((source / path).read_bytes()).hexdigest(),
        }
        for path in sorted(
            [
                "agent-design.md",
                "agent-graph.mmd",
                "agent-runtime.yaml",
                "workflow-descriptor.yaml",
            ]
        )
    ]


def test_staging_accepts_a_source_manifest_that_matches_the_payload(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    expected_manifest = _write_source_manifest(source)
    handle, store = _selection(tmp_path, source)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    assert (staged.root / "package-manifest.json").read_bytes() == expected_manifest


def test_staging_rejects_a_source_manifest_that_does_not_match_the_payload(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    _write_source_manifest(source)
    (source / "agent-design.md").write_text("changed", encoding="utf-8")
    handle, store = _selection(tmp_path, source)

    with pytest.raises(PackageStagingError, match="manifest does not match"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_imports_a_human_selected_zip_through_the_private_copy(
    tmp_path: Path,
) -> None:
    archive = _archive_package(tmp_path)
    handle, store = _archive_selection(tmp_path, archive)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    assert staged.root.is_dir()
    assert staged.file_count == 4
    assert staged.byte_count > 0
    assert not list((tmp_path / "private").glob(".extract-*"))


def test_staging_rejects_a_portable_zip_without_a_source_manifest(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    handle, store = _archive_selection(tmp_path, archive)

    with pytest.raises(PackageStagingError, match="portable ZIP.*manifest"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_verifies_a_human_selected_publisher_signed_zip(
    tmp_path: Path,
) -> None:
    key_id = "publisher.example.v1"
    private_key = Ed25519PrivateKey.generate()
    archive = _signed_archive(
        tmp_path, key_id=key_id, private_key=private_key.private_bytes_raw()
    )
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_publisher_zip(archive, now=NOW)

    staged = PrivatePackageStager(
        store=store,
        private_root=tmp_path / "private",
        trusted_keys=lambda: {key_id: private_key.public_key().public_bytes_raw()},
    ).stage(handle, now=NOW)

    assert staged.trust == "publisher_signature"
    assert staged.publisher_key_id == key_id
    assert not (staged.root / "package-signature.json").exists()


def test_staging_rejects_an_untrusted_publisher_signed_zip(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    archive = _signed_archive(
        tmp_path,
        key_id="publisher.example.v1",
        private_key=private_key.private_bytes_raw(),
    )
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=archive.parent, store=store
    ).select_publisher_zip(archive, now=NOW)

    with pytest.raises(PackageStagingError, match="publisher signature"):
        PrivatePackageStager(
            store=store,
            private_root=tmp_path / "private",
            trusted_keys=lambda: {},
        ).stage(handle, now=NOW)


@pytest.mark.parametrize(
    "member_name", ["../agent-runtime.yaml", "/agent-runtime.yaml"]
)
def test_staging_rejects_zip_members_that_escape_the_package(
    tmp_path: Path, member_name: str
) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    archive = allowed_root / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(member_name, "not a DAR package")
    handle, store = _archive_selection(tmp_path, archive)

    with pytest.raises(PackageStagingError, match="unsafe archive member"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_zip_symlink_members(tmp_path: Path) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    archive = allowed_root / "unsafe.zip"
    member = zipfile.ZipInfo("link")
    member.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(member, "outside")
    handle, store = _archive_selection(tmp_path, archive)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_zip_members_above_the_file_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    archive = allowed_root / "oversize.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("agent-design.md", "oversize")
    monkeypatch.setattr("dar_workflow_server.staging.MAX_FILE_BYTES", 4)
    handle, store = _archive_selection(tmp_path, archive)

    with pytest.raises(PackageStagingError, match="file exceeds size limit"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_duplicate_zip_members(tmp_path: Path) -> None:
    allowed_root = tmp_path / "packages"
    allowed_root.mkdir()
    archive = allowed_root / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("agent-design.md", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            package.writestr("agent-design.md", "second")
    handle, store = _archive_selection(tmp_path, archive)

    with pytest.raises(PackageStagingError, match="duplicate"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_creates_missing_parent_directories_for_zip_members(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    (source / "assets").mkdir()
    (source / "assets" / "input.txt").write_text("input", encoding="utf-8")
    _write_source_manifest(source)
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(source).as_posix())
    handle, store = _archive_selection(tmp_path, archive)

    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    assert (staged.root / "assets" / "input.txt").read_text(encoding="utf-8") == "input"


def test_staging_does_not_follow_nested_symlinks(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    os.symlink(tmp_path / "outside", source / "unexpected-link")
    handle, store = _selection(tmp_path, source)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_non_regular_entries(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    os.mkfifo(source / "unexpected-fifo")
    handle, store = _selection(tmp_path, source)

    with pytest.raises(PackageStagingError, match="non-regular"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staged_copy_does_not_change_when_source_changes_after_staging(
    tmp_path: Path,
) -> None:
    source = _source_package(tmp_path)
    original = (source / "agent-design.md").read_text(encoding="utf-8")
    handle, store = _selection(tmp_path, source)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
        handle, now=NOW
    )

    (source / "agent-design.md").write_text("changed", encoding="utf-8")

    assert (staged.root / "agent-design.md").read_text(encoding="utf-8") == original


def test_staging_rejects_a_parent_path_swapped_for_a_symlink(tmp_path: Path) -> None:
    source = _source_package(tmp_path)
    handle, store = _selection(tmp_path, source)
    original_parent = source.parent
    moved_parent = tmp_path / "moved-packages"
    original_parent.rename(moved_parent)
    os.symlink(tmp_path / "outside", original_parent)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_staging_rejects_a_zip_parent_path_swapped_for_a_symlink(
    tmp_path: Path,
) -> None:
    archive = _archive_package(tmp_path)
    handle, store = _archive_selection(tmp_path, archive)
    original_parent = archive.parent
    moved_parent = tmp_path / "moved-packages"
    original_parent.rename(moved_parent)
    os.symlink(tmp_path / "outside", original_parent)

    with pytest.raises(PackageStagingError, match="symlink"):
        PrivatePackageStager(store=store, private_root=tmp_path / "private").stage(
            handle, now=NOW
        )


def test_invalid_dar_package_is_not_published_to_private_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages" / "invalid"
    source.mkdir(parents=True)
    (source / "agent-runtime.yaml").write_text("not: valid", encoding="utf-8")
    handle, store = _selection(tmp_path, source)
    private_root = tmp_path / "private"

    with pytest.raises(PackageStagingError, match="DAR validation"):
        PrivatePackageStager(store=store, private_root=private_root).stage(
            handle, now=NOW
        )

    assert not list(private_root.glob("package-*"))
