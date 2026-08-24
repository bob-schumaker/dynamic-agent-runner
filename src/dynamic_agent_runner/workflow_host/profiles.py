"""Installation identity and human-created local model profiles."""

from __future__ import annotations

import getpass
import ipaddress
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from urllib.parse import urlsplit

from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)
from dynamic_agent_runner.local_models import (
    LocalOpenAIEndpointConfig,
    create_local_openai_adapter,
)
from dynamic_agent_runner.openai_client import OpenAIClientAdapter


class LocalModelProfileError(ValueError):
    """Raised when a local model profile is invalid or unavailable."""


@dataclass(frozen=True)
class InstallationIdentityProvider:
    """Derive the v1 installation principal from the local OS-user boundary."""

    @property
    def principal(self) -> str:
        username = getpass.getuser()
        if not username:
            raise LocalModelProfileError("local OS user is unavailable")
        uid = _uid()
        return f"local-os-user-v1:{uid}:{username}"


@dataclass(frozen=True)
class LocalModelProfile:
    """An immutable local-model capability record."""

    profile_id: str
    model_id: str
    adapter_id: str
    base_url: str
    profile_requirement: str
    capabilities: frozenset[str]


class LocalModelProfileControlPlane:
    """Human-only creation and lookup boundary for v1 local model profiles."""

    def __init__(self, *, store: PrivateStateStore) -> None:
        self._store = store
        self._identity = InstallationIdentityProvider()

    def create(
        self,
        *,
        model_id: str,
        adapter_id: str,
        base_url: str,
        capabilities: Iterable[str],
        profile_requirement: str = "local-general-model",
    ) -> LocalModelProfile:
        """Persist an immutable record for the one supported local adapter type."""

        _nonempty(model_id, "model_id")
        _nonempty(profile_requirement, "profile_requirement")
        if adapter_id != "strict-local-adapter-v1":
            raise LocalModelProfileError(
                "adapter_id must identify a supported local adapter"
            )
        _validate_loopback_base_url(base_url)
        capability_set = frozenset(capabilities)
        if not capability_set or any(
            not isinstance(item, str) or not item for item in capability_set
        ):
            raise LocalModelProfileError("capabilities must contain non-empty strings")
        handle = self._store.issue(
            kind="local_model_profile",
            owner=self._identity.principal,
            payload={
                "model_id": model_id,
                "adapter_id": adapter_id,
                "base_url": base_url,
                "profile_requirement": profile_requirement,
                "capabilities": sorted(capability_set),
            },
            expires_at=datetime.max.replace(tzinfo=UTC),
            now=datetime.now(UTC),
        )
        return LocalModelProfile(
            handle,
            model_id,
            adapter_id,
            base_url,
            profile_requirement,
            capability_set,
        )

    def load(self, profile_id: str) -> LocalModelProfile:
        """Load an immutable profile owned by this installation principal."""

        try:
            record = self._store.load(
                profile_id,
                expected_kind="local_model_profile",
                owner=self._identity.principal,
                now=datetime.now(UTC),
            )
        except OpaqueRecordError as error:
            raise LocalModelProfileError(str(error)) from error
        payload = record.payload
        try:
            model_id = payload["model_id"]
            adapter_id = payload["adapter_id"]
            base_url = payload["base_url"]
            profile_requirement = payload["profile_requirement"]
            capabilities = frozenset(payload["capabilities"])
        except (KeyError, TypeError) as error:
            raise LocalModelProfileError("local model profile is invalid") from error
        _nonempty(model_id, "model_id")
        _nonempty(profile_requirement, "profile_requirement")
        if adapter_id != "strict-local-adapter-v1":
            raise LocalModelProfileError("local model profile is invalid")
        _validate_loopback_base_url(base_url)
        if not capabilities or any(
            not isinstance(item, str) or not item for item in capabilities
        ):
            raise LocalModelProfileError("local model profile is invalid")
        return LocalModelProfile(
            profile_id,
            model_id,
            adapter_id,
            base_url,
            profile_requirement,
            capabilities,
        )


def create_local_adapter(profile: LocalModelProfile) -> OpenAIClientAdapter:
    """Construct the profile's host-owned loopback model adapter."""

    if profile.adapter_id != "strict-local-adapter-v1":
        raise LocalModelProfileError("local model profile is invalid")
    _validate_loopback_base_url(profile.base_url)
    return create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url=profile.base_url,
            model_aliases=(profile.model_id, "local-model"),
            expected_model_id=profile.model_id,
        )
    )


def _uid() -> str:
    getuid = getattr(os, "getuid", None)
    return str(getuid()) if getuid is not None else "no-uid"


def _nonempty(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise LocalModelProfileError(f"{name} must be a non-empty string")


def _validate_loopback_base_url(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise LocalModelProfileError("base_url must be a non-empty loopback URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise LocalModelProfileError("base_url must be a loopback URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is None
        or not _is_loopback_host(parsed.hostname)
    ):
        raise LocalModelProfileError("base_url must be a loopback URL")


def _is_loopback_host(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
