"""Package-handle-only preflight for DAR authoring workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    ReviewedCapabilityTemplate,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.policy import (
    CapabilityResolution,
    PolicyCompilationError,
    WorkflowPolicy,
    compile_workflow_policy,
    resolve_capabilities,
)
from dynamic_agent_runner.workflow_host.staging import (
    PackageStagingError,
    PrivatePackageStager,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
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
        descriptor_validators: ExecutionDescriptorValidatorRegistry | None = None,
        reviewed_templates: ReviewedCapabilityTemplateControlPlane | None = None,
        current_reviewed_template_provider: (
            Callable[[str], ReviewedCapabilityTemplate] | None
        ) = None,
    ) -> None:
        self._stager = stager
        self._catalog = catalog
        self._available_capabilities = frozenset(available_capabilities)
        self._capability_catalog = capability_catalog
        self._descriptor_validators = descriptor_validators
        self._reviewed_templates = reviewed_templates
        self._current_reviewed_template_provider = current_reviewed_template_provider

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
                revision,
                capability_catalog=self._capability_catalog,
                descriptor_validators=self._descriptor_validators,
            )
            self._validate_reviewed_templates(policy)
        except (
            PackageStagingError,
            PackageCatalogError,
            PolicyCompilationError,
            PackagePreflightError,
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

    def _validate_reviewed_templates(self, policy: WorkflowPolicy) -> None:
        declarations = policy.declared_reviewed_capability_tools
        if not declarations:
            return
        if (
            len(declarations) != 1
            or self._reviewed_templates is None
            or self._current_reviewed_template_provider is None
        ):
            raise PackagePreflightError("reviewed template is unavailable")
        try:
            declaration = declarations[0]
            current = self._current_reviewed_template_provider(
                declaration.capability_id
            )
            self._reviewed_templates.resolve_declared(
                capability_id=declaration.capability_id,
                contract_version=declaration.contract_version,
                template_digest=declaration.template_digest,
                input_fields=declaration.input_fields,
                current_template=current,
            )
        except Exception as error:  # noqa: BLE001 - host provider boundary varies.
            raise PackagePreflightError("reviewed template is unavailable") from error
