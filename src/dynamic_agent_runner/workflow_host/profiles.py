"""Installation identity and human-created local model profiles."""

from __future__ import annotations

import getpass
import hashlib
import ipaddress
import json
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
from dynamic_agent_runner.openai_client import (
    OpenAIClientAdapter,
    OpenAIProviderConfig,
    create_openai_adapter_from_provider_config,
)
from dynamic_agent_runner.apple_foundation_models import (
    preflight_apple_foundation_models,
)
from dynamic_agent_runner.workflow_host.fastmail_triage_model import (
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    FASTMAIL_TRIAGE_MODEL_ALIAS,
    create_fastmail_triage_llama_cpp_adapter as _create_fastmail_triage_llama_cpp_adapter,
)
from dynamic_agent_runner.workflow_host.floorplan_vision_model import (
    FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID,
    FLOORPLAN_VISION_MODEL_ID,
    create_floorplan_vision_llama_cpp_adapter as _create_floorplan_vision_llama_cpp_adapter,
)


FASTMAIL_TRIAGE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"


class LocalModelProfileError(ValueError):
    """Raised when a local model profile is invalid or unavailable."""


_PROFILE_REQUIREMENT_CAPABILITIES = {
    "local-general-model": frozenset({"text_generation"}),
    "local-multimodal-model-v1": frozenset({"text_generation", "multimodal_input"}),
    "general-language-model-v1": frozenset({"text_generation"}),
}


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
    """An immutable host execution-profile capability record."""

    profile_id: str
    model_id: str
    execution_model_id: str
    adapter_id: str
    base_url: str | None
    profile_requirement: str
    capabilities: frozenset[str]
    profile_digest: str


class LocalModelProfileControlPlane:
    """Human-only creation and lookup boundary for host execution profiles."""

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
        execution_model_id: str = "local-model",
        profile_requirement: str = "local-general-model",
    ) -> LocalModelProfile:
        """Persist an immutable record for the supported local adapter type."""

        _nonempty(model_id, "model_id")
        _nonempty(execution_model_id, "execution_model_id")
        _nonempty(profile_requirement, "profile_requirement")
        if adapter_id != "strict-local-adapter-v1":
            raise LocalModelProfileError(
                "adapter_id must identify a supported local adapter"
            )
        _validate_loopback_base_url(base_url)
        return self._issue(
            model_id=model_id,
            execution_model_id=execution_model_id,
            adapter_id=adapter_id,
            base_url=base_url,
            profile_requirement=profile_requirement,
            capabilities=capabilities,
        )

    def create_hosted_openai(
        self,
        *,
        model_id: str,
        base_url: str,
        capabilities: Iterable[str],
        execution_model_id: str = "local-model",
        profile_requirement: str = "general-language-model-v1",
    ) -> LocalModelProfile:
        """Persist one human-configured non-local OpenAI-compatible profile."""

        _nonempty(model_id, "model_id")
        _nonempty(execution_model_id, "execution_model_id")
        _nonempty(profile_requirement, "profile_requirement")
        _validate_remote_base_url(base_url)
        return self._issue(
            model_id=model_id,
            execution_model_id=execution_model_id,
            adapter_id="hosted-openai-adapter-v1",
            base_url=base_url,
            profile_requirement=profile_requirement,
            capabilities=capabilities,
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
            execution_model_id = payload["execution_model_id"]
            adapter_id = payload["adapter_id"]
            base_url = payload["base_url"]
            profile_requirement = payload["profile_requirement"]
            capabilities = frozenset(payload["capabilities"])
            profile_digest = payload["profile_digest"]
        except (KeyError, TypeError) as error:
            raise LocalModelProfileError("local model profile is invalid") from error
        _nonempty(model_id, "model_id")
        _nonempty(execution_model_id, "execution_model_id")
        _nonempty(profile_requirement, "profile_requirement")
        if adapter_id == "strict-local-adapter-v1":
            _validate_loopback_base_url(base_url)
        elif adapter_id in {
            "apple-foundation-models-adapter-v1",
            FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
            FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID,
        }:
            if base_url is not None:
                raise LocalModelProfileError("local model profile is invalid")
        elif adapter_id == "hosted-openai-adapter-v1":
            _validate_remote_base_url(base_url)
        else:
            raise LocalModelProfileError("local model profile is invalid")
        if not capabilities or any(
            not isinstance(item, str) or not item for item in capabilities
        ):
            raise LocalModelProfileError("local model profile is invalid")
        _validate_profile_contract(
            adapter_id=adapter_id,
            profile_requirement=profile_requirement,
            capabilities=capabilities,
        )
        if not isinstance(profile_digest, str) or profile_digest != _profile_digest(
            adapter_id=adapter_id,
            model_id=model_id,
            execution_model_id=execution_model_id,
            base_url=base_url,
            profile_requirement=profile_requirement,
            capabilities=capabilities,
        ):
            raise LocalModelProfileError("local model profile is invalid")
        return LocalModelProfile(
            profile_id,
            model_id,
            execution_model_id,
            adapter_id,
            base_url,
            profile_requirement,
            capabilities,
            profile_digest,
        )

    def create_apple(self, *, model_id: str) -> LocalModelProfile:
        """Persist one human-confirmed on-device Apple model profile."""

        _nonempty(model_id, "model_id")
        preflight_apple_foundation_models()
        return self._issue(
            model_id=model_id,
            execution_model_id=model_id,
            adapter_id="apple-foundation-models-adapter-v1",
            base_url=None,
            profile_requirement="local-general-model",
            capabilities={"text_generation"},
        )

    def create_fastmail_triage_llama_cpp(self) -> LocalModelProfile:
        """Persist the fixed offline Qwen profile for Fastmail triage only."""

        return self._issue(
            model_id=FASTMAIL_TRIAGE_MODEL_ID,
            execution_model_id=FASTMAIL_TRIAGE_MODEL_ALIAS,
            adapter_id=FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
            base_url=None,
            profile_requirement="local-general-model",
            capabilities={"text_generation"},
        )

    def create_floorplan_vision_llama_cpp(self) -> LocalModelProfile:
        """Persist the exact configured local vision profile for floorplans."""

        return self._issue(
            model_id=FLOORPLAN_VISION_MODEL_ID,
            execution_model_id=FLOORPLAN_VISION_MODEL_ID,
            adapter_id=FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID,
            base_url=None,
            profile_requirement="local-multimodal-model-v1",
            capabilities={"text_generation", "multimodal_input"},
        )

    def _issue(
        self,
        *,
        model_id: str,
        execution_model_id: str,
        adapter_id: str,
        base_url: str | None,
        profile_requirement: str,
        capabilities: Iterable[str],
    ) -> LocalModelProfile:
        capability_set = frozenset(capabilities)
        if not capability_set or any(
            not isinstance(item, str) or not item for item in capability_set
        ):
            raise LocalModelProfileError("capabilities must contain non-empty strings")
        _validate_profile_contract(
            adapter_id=adapter_id,
            profile_requirement=profile_requirement,
            capabilities=capability_set,
        )
        profile_digest = _profile_digest(
            adapter_id=adapter_id,
            model_id=model_id,
            execution_model_id=execution_model_id,
            base_url=base_url,
            profile_requirement=profile_requirement,
            capabilities=capability_set,
        )
        handle = self._store.issue(
            kind="local_model_profile",
            owner=self._identity.principal,
            payload={
                "model_id": model_id,
                "execution_model_id": execution_model_id,
                "adapter_id": adapter_id,
                "base_url": base_url,
                "profile_requirement": profile_requirement,
                "capabilities": sorted(capability_set),
                "profile_digest": profile_digest,
            },
            expires_at=datetime.max.replace(tzinfo=UTC),
            now=datetime.now(UTC),
        )
        return LocalModelProfile(
            handle,
            model_id,
            execution_model_id,
            adapter_id,
            base_url,
            profile_requirement,
            capability_set,
            profile_digest,
        )


def create_local_adapter(profile: LocalModelProfile) -> OpenAIClientAdapter:
    """Construct the profile's host-owned loopback model adapter."""

    if profile.adapter_id != "strict-local-adapter-v1":
        raise LocalModelProfileError("local model profile is invalid")
    _validate_loopback_base_url(profile.base_url)
    return create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url=profile.base_url,
            model_aliases=(profile.execution_model_id,),
            expected_model_id=profile.model_id,
        )
    )


def create_fastmail_triage_llama_cpp_adapter(profile: LocalModelProfile):
    """Create the pinned direct Qwen adapter for its one matching profile."""

    if (
        profile.adapter_id != FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID
        or profile.model_id != FASTMAIL_TRIAGE_MODEL_ID
        or profile.execution_model_id != FASTMAIL_TRIAGE_MODEL_ALIAS
        or profile.base_url is not None
    ):
        raise LocalModelProfileError("local model profile is invalid")
    return _create_fastmail_triage_llama_cpp_adapter()


def create_floorplan_vision_llama_cpp_adapter(profile: LocalModelProfile):
    """Create the pinned vision adapter only for its exact configured profile."""

    if (
        profile.adapter_id != FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID
        or profile.model_id != FLOORPLAN_VISION_MODEL_ID
        or profile.execution_model_id != FLOORPLAN_VISION_MODEL_ID
        or profile.base_url is not None
    ):
        raise LocalModelProfileError("local model profile is invalid")
    return _create_floorplan_vision_llama_cpp_adapter()


def create_hosted_openai_adapter(profile: LocalModelProfile) -> OpenAIClientAdapter:
    """Construct the host-owned adapter for a configured hosted profile."""

    if profile.adapter_id != "hosted-openai-adapter-v1":
        raise LocalModelProfileError("local model profile is invalid")
    _validate_remote_base_url(profile.base_url)
    return create_openai_adapter_from_provider_config(
        OpenAIProviderConfig(
            base_url=profile.base_url,
            provider_name="hosted-openai-compatible",
            discover_default_auth=False,
        ),
        models=(profile.execution_model_id,),
        is_local=False,
        execution_profile_adapter_id="hosted-openai-adapter-v1",
        model_id_mapping={profile.execution_model_id: profile.model_id},
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


def _validate_remote_base_url(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise LocalModelProfileError("base_url must be a non-empty HTTPS URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise LocalModelProfileError("base_url must be an HTTPS URL") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LocalModelProfileError("base_url must be an HTTPS URL")


def _profile_digest(
    *,
    adapter_id: str,
    model_id: str,
    execution_model_id: str,
    base_url: str | None,
    profile_requirement: str,
    capabilities: frozenset[str],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "format_version": 1,
                "adapter_id": adapter_id,
                "model_id": model_id,
                "execution_model_id": execution_model_id,
                "base_url_identity": _base_url_identity(base_url),
                "profile_requirement": profile_requirement,
                "capabilities": sorted(capabilities),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _base_url_identity(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    return {
        "scheme": parsed.scheme.lower(),
        "hostname": parsed.hostname.lower() if parsed.hostname else None,
        "port": parsed.port,
        "path": parsed.path or "/",
    }


def _validate_profile_contract(
    *,
    adapter_id: object,
    profile_requirement: object,
    capabilities: frozenset[str],
) -> None:
    expected_capabilities = _PROFILE_REQUIREMENT_CAPABILITIES.get(profile_requirement)
    if expected_capabilities is None or capabilities != expected_capabilities:
        raise LocalModelProfileError("local model profile is invalid")
    if adapter_id in {
        "strict-local-adapter-v1",
        "apple-foundation-models-adapter-v1",
        FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    }:
        if profile_requirement != "local-general-model":
            raise LocalModelProfileError("local model profile is invalid")
        return
    if adapter_id == FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID:
        if profile_requirement != "local-multimodal-model-v1":
            raise LocalModelProfileError("local model profile is invalid")
        return
    if (
        adapter_id != "hosted-openai-adapter-v1"
        or profile_requirement != "general-language-model-v1"
    ):
        raise LocalModelProfileError("local model profile is invalid")


def _is_loopback_host(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
