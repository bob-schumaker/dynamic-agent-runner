"""Immutable catalog records for privately staged DAR packages."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dynamic_agent_runner import load_agent_package_workflow

from dar_workflow_server.staging import StagedPackage


class PackageCatalogError(ValueError):
    """Raised when a staged package cannot become a catalog revision."""


@dataclass(frozen=True)
class CatalogPackageRevision:
    """One immutable package identity and private staged-root binding."""

    package_id: str
    revision_digest: str
    package_root: Path


class PackageCatalog:
    """Retain staged package revisions without creating executable aliases."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._path = root / "packages.json"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        mode = os.lstat(root).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise PackageCatalogError("package catalog root is not a directory")

    def import_staged(self, staged: StagedPackage) -> CatalogPackageRevision:
        """Record one DAR-validated staged copy by package ID and content digest."""

        package_root = Path(staged.root)
        try:
            workflow = load_agent_package_workflow(str(package_root))
        except Exception as error:
            raise PackageCatalogError("staged package fails DAR validation") from error
        package_id = workflow.runtime_manifest.package_id
        if not package_id:
            raise PackageCatalogError("staged package has no package_id")
        if not _is_digest(staged.digest):
            raise PackageCatalogError("staged package digest is invalid")
        revision = CatalogPackageRevision(package_id, staged.digest, package_root)
        packages = self._read()
        revisions = packages.setdefault(package_id, {})
        existing = revisions.get(staged.digest)
        if existing is not None:
            return _revision_from_mapping(package_id, staged.digest, existing)
        revisions[staged.digest] = {"package_root": str(package_root)}
        self._write(packages)
        return revision

    def revisions(self, package_id: str) -> tuple[CatalogPackageRevision, ...]:
        """Return all retained immutable revisions for one portable package ID."""

        if not isinstance(package_id, str) or not package_id:
            raise PackageCatalogError("package_id must be a non-empty string")
        revisions = self._read().get(package_id, {})
        if not isinstance(revisions, Mapping):
            raise PackageCatalogError("package catalog is invalid")
        return tuple(
            _revision_from_mapping(package_id, digest, revisions[digest])
            for digest in sorted(revisions)
        )

    def revision(self, package_id: str, revision_digest: str) -> CatalogPackageRevision:
        """Resolve one retained revision by its immutable package identity."""

        for revision in self.revisions(package_id):
            if revision.revision_digest == revision_digest:
                return revision
        raise PackageCatalogError("package revision is not cataloged")

    def _read(self) -> dict[str, dict[str, dict[str, str]]]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict) or not isinstance(value.get("packages"), dict):
            raise PackageCatalogError("package catalog is invalid")
        return value["packages"]

    def _write(self, packages: Mapping[str, Any]) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"packages": packages}, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._path)


def _revision_from_mapping(
    package_id: str, digest: str, value: object
) -> CatalogPackageRevision:
    if not _is_digest(digest) or not isinstance(value, Mapping):
        raise PackageCatalogError("package catalog is invalid")
    root = value.get("package_root")
    if not isinstance(root, str):
        raise PackageCatalogError("package catalog is invalid")
    return CatalogPackageRevision(package_id, digest, Path(root))


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
