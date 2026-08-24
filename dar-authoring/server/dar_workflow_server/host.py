"""Private local host configuration and no-tool runner composition."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dar_workflow_server.catalog import PackageCatalog
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy
from dar_workflow_server.policy import compile_workflow_policy, resolve_capabilities
from dar_workflow_server.preparation import (
    PreparedWorkflowInput,
    WorkflowInvocationPreparationService,
)
from dar_workflow_server.profiles import (
    LocalModelProfileControlPlane,
    create_local_adapter,
)
from dar_workflow_server.registration import (
    WorkflowRegistration,
    WorkflowRegistrationService,
)
from dar_workflow_server.runner import (
    DryRunDarWorkflowResult,
    RunDarWorkflowRequest,
    RunDarWorkflowResult,
    WorkflowRunner,
)
from dar_workflow_server.staging import PrivatePackageStager
from dar_workflow_server.state import PrivateStateStore


class LocalWorkflowHostError(ValueError):
    """Raised when required human-owned host configuration is unavailable."""


@dataclass(frozen=True)
class LocalWorkflowHostConfiguration:
    """Private setup record for one OS-user local workflow host."""

    package_root: Path
    profile_id: str


def configure_local_host(
    *, root: Path, package_root: Path, model_id: str, base_url: str
) -> LocalWorkflowHostConfiguration:
    """Create the human-owned v1 local model profile and host configuration."""

    _validate_root(root)
    _validate_package_root(package_root)
    store = PrivateStateStore(root)
    profile = LocalModelProfileControlPlane(store=store).create(
        model_id=model_id,
        adapter_id="strict-local-adapter-v1",
        base_url=base_url,
        capabilities={"text_generation"},
    )
    configuration = LocalWorkflowHostConfiguration(package_root, profile.profile_id)
    _write_configuration(root, configuration)
    return configuration


class LocalWorkflowHost:
    """One local-principal composition root for sealed no-tool workflow runs."""

    def __init__(
        self,
        *,
        configuration: LocalWorkflowHostConfiguration,
        sources: PackageSourceSelectionPolicy,
        stager: PrivatePackageStager,
        catalog: PackageCatalog,
        registrations: WorkflowRegistrationService,
        preparation: WorkflowInvocationPreparationService,
        runner: WorkflowRunner,
    ) -> None:
        self._configuration = configuration
        self._sources = sources
        self._stager = stager
        self._catalog = catalog
        self._registrations = registrations
        self._preparation = preparation
        self._runner = runner

    @classmethod
    def open(cls, root: Path) -> LocalWorkflowHost:
        """Open a configured local host for the current OS user."""

        _validate_root(root)
        configuration = _read_configuration(root)
        store = PrivateStateStore(root)
        profiles = LocalModelProfileControlPlane(store=store)
        profile = profiles.load(configuration.profile_id)
        catalog = PackageCatalog(root / "catalog")
        registrations = WorkflowRegistrationService(
            profiles=profiles,
            configured_profile_id=profile.profile_id,
            root=root / "registrations",
        )
        preparation = WorkflowInvocationPreparationService(
            registrations=registrations, catalog=catalog, store=store
        )
        return cls(
            configuration=configuration,
            sources=PackageSourceSelectionPolicy(
                allowed_root=configuration.package_root, store=store
            ),
            stager=PrivatePackageStager(store=store, private_root=root / "staging"),
            catalog=catalog,
            registrations=registrations,
            preparation=preparation,
            runner=WorkflowRunner(
                registrations=registrations,
                catalog=catalog,
                preparation=preparation,
                model_adapter=create_local_adapter(profile),
            ),
        )

    def select_package(self, path: Path, *, now: datetime) -> str:
        """Return an opaque handle for one human-selected package directory."""

        return self._sources.select_directory(path, now=now)

    def register(
        self, *, workflow_id: str, package_source_handle: str, now: datetime
    ) -> WorkflowRegistration:
        """Stage, compile, and bind a human-selected package to a local alias."""

        revision = self._catalog.import_staged(
            self._stager.stage(package_source_handle, now=now)
        )
        policy = compile_workflow_policy(revision)
        return self._registrations.register(
            workflow_id=workflow_id,
            policy=policy,
            capability_resolution=resolve_capabilities(
                policy, available_capabilities={"local_model"}
            ),
        )

    def prepare(
        self, *, workflow_id: str, prompt: str, now: datetime
    ) -> PreparedWorkflowInput:
        """Seal a local CLI prompt for a registered workflow."""

        return self._preparation.prepare(
            workflow_id=workflow_id, prompt=prompt, now=now
        )

    def dry_run(
        self, *, workflow_id: str, prepared_input_id: str, now: datetime
    ) -> DryRunDarWorkflowResult:
        """Validate a sealed run without invoking a model or consuming input."""

        return self._runner.dry_run(_request(workflow_id, prepared_input_id), now=now)

    def run(
        self, *, workflow_id: str, prepared_input_id: str, now: datetime
    ) -> RunDarWorkflowResult:
        """Execute a sealed local no-tool workflow through the one runner."""

        return self._runner.run(_request(workflow_id, prepared_input_id), now=now)


def _request(workflow_id: str, prepared_input_id: str) -> RunDarWorkflowRequest:
    return RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": workflow_id,
            "prepared_input_id": prepared_input_id,
        }
    )


def _configuration_path(root: Path) -> Path:
    return root / "host.json"


def _read_configuration(root: Path) -> LocalWorkflowHostConfiguration:
    try:
        value = json.loads(_configuration_path(root).read_text(encoding="utf-8"))
        package_root = Path(value["package_root"])
        profile_id = value["profile_id"]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise LocalWorkflowHostError("local host is not configured") from error
    _validate_package_root(package_root)
    if not isinstance(profile_id, str) or not profile_id.startswith("v1."):
        raise LocalWorkflowHostError("local host configuration is invalid")
    return LocalWorkflowHostConfiguration(package_root, profile_id)


def _write_configuration(root: Path, value: LocalWorkflowHostConfiguration) -> None:
    destination = _configuration_path(root)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "format_version": 1,
                "package_root": str(value.package_root),
                "profile_id": value.profile_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def _validate_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("host root must be an absolute canonical path")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def _validate_package_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("package root must be an absolute canonical path")
