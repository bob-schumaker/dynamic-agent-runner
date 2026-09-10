"""Package-handle-only preflight for DAR authoring workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.capabilities import CapabilityCatalog
from dynamic_agent_runner.workflow_host.policy import (
    CapabilityResolution,
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
from dynamic_agent_runner.workflow_host.staging import (
    PackageStagingError,
    PrivatePackageStager,
)


class PackagePreflightError(ValueError):
    """Raised when an opaque package handle cannot be preflighted."""


@dataclass(frozen=True)
class PackagePreflightResult:
    """A closed, non-executing package-policy result."""

    package_id: str
    revision_digest: str
    workflow_policy_digest: str
    capability_resolution: CapabilityResolution


class PackagePreflightService:
    """Stage and inspect a package without creating a registration or alias."""

    def __init__(
        self,
        *,
        stager: PrivatePackageStager,
        catalog: PackageCatalog,
        available_capabilities: Iterable[str],
        capability_catalog: CapabilityCatalog | None = None,
    ) -> None:
        self._stager = stager
        self._catalog = catalog
        self._available_capabilities = frozenset(available_capabilities)
        self._capability_catalog = capability_catalog

    def preflight(
        self, package_source_handle: str, *, now: datetime
    ) -> PackagePreflightResult:
        """Return only policy identity and a deterministic capability result."""

        if not isinstance(
            package_source_handle, str
        ) or not package_source_handle.startswith("v1."):
            raise PackagePreflightError(
                "preflight requires an opaque package source handle"
            )
        try:
            staged = self._stager.stage(package_source_handle, now=now)
            revision = self._catalog.import_staged(staged)
            policy = compile_workflow_policy(
                revision, capability_catalog=self._capability_catalog
            )
        except (
            PackageStagingError,
            PackageCatalogError,
            PolicyCompilationError,
        ) as error:
            raise PackagePreflightError("package preflight failed") from error
        return PackagePreflightResult(
            package_id=revision.package_id,
            revision_digest=revision.revision_digest,
            workflow_policy_digest=policy.policy_digest,
            capability_resolution=resolve_capabilities(
                policy, available_capabilities=self._available_capabilities
            ),
        )
