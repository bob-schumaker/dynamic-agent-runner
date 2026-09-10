"""Tests for immutable DAR capability-contract values and resolution."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    CapabilityContract,
    CapabilityError,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
    BUILTIN_CAPABILITY_CONTRACTS,
    ProviderAvailability,
    UnavailableCapability,
)


def _contract(*, features: tuple[str, ...] = ("image", "text")) -> CapabilityContract:
    return CapabilityContract(
        capability_id="model.execution.test.v1",
        contract_version="1",
        contract_digest="a" * 64,
        features=features,
    )


def _requirements() -> CapabilityRequirements:
    return CapabilityRequirements(
        required_capabilities=(
            CapabilityRequirement(
                capability_id="model.execution.test.v1",
                contract_version="1",
                contract_digest="a" * 64,
                required_features=("image",),
            ),
        ),
        bindings={"runner": "model.execution.test.v1"},
    )


def _provider(
    *,
    availability: ProviderAvailability = ProviderAvailability.AVAILABLE,
    features: tuple[str, ...] = ("image", "text"),
    conforms: bool = True,
) -> CapabilityProvider:
    return CapabilityProvider(
        provider_id="private-test-provider",
        contract=_contract(features=features),
        availability=availability,
        conformance_passed=conforms,
    )


def test_requirement_digest_is_canonical_and_excludes_declared_digest() -> None:
    requirements = _requirements()

    assert requirements.canonical_bytes == (
        b'{"bindings":{"runner":{"capability_id":"model.execution.test.v1"}},'
        b'"format_version":1,"required_capabilities":[{"capability_id":'
        b'"model.execution.test.v1","contract_digest":"'
        + b"a" * 64
        + b'","contract_version":"1","required_features":["image"]}]}'
    )
    assert requirements.digest == sha256(requirements.canonical_bytes).hexdigest()


def test_empty_requirements_are_canonical_and_distinct_from_a_requirement() -> None:
    empty = CapabilityRequirements()

    assert empty.digest == sha256(empty.canonical_bytes).hexdigest()
    assert empty.digest != _requirements().digest


@pytest.mark.parametrize(
    "factory",
    (
        lambda: CapabilityContract(
            "model.execution.test.v1", "1", "not-a-digest", ("image",)
        ),
        lambda: CapabilityContract(
            "model.execution.test.v1", "1", "A" * 64, ("image",)
        ),
        lambda: CapabilityContract(
            "model.execution.test.v1", "1", "a" * 64, ("text", "image")
        ),
        lambda: CapabilityContract(
            "model.execution.cafe\u0301.v1", "1", "a" * 64, ("image",)
        ),
        lambda: CapabilityRequirement(
            "model.execution.test.v1", "1", "a" * 64, ("image", "image")
        ),
        lambda: CapabilityRequirements(
            required_capabilities=(
                CapabilityRequirement("b", "1", "a" * 64, ()),
                CapabilityRequirement("a", "1", "a" * 64, ()),
            )
        ),
    ),
)
def test_contract_values_reject_noncanonical_values(factory: object) -> None:
    with pytest.raises(CapabilityError):
        factory()  # type: ignore[operator]


def test_requirements_reject_invalid_bindings_and_unavailable_features() -> None:
    requirement = CapabilityRequirement(
        "model.execution.test.v1", "1", "a" * 64, ("image",)
    )

    with pytest.raises(CapabilityError, match="binding"):
        CapabilityRequirements((requirement,), {"runner": "missing"})

    resolution = CapabilityCatalog((_contract(features=("text",)),), ()).resolve(
        CapabilityRequirements((requirement,), {"runner": "model.execution.test.v1"})
    )

    assert len(resolution.unavailable) == 1
    assert resolution.unavailable[0].capability_id == "model.execution.test.v1"
    assert resolution.unavailable[0].classification is None


def test_catalog_selects_exact_conforming_available_provider() -> None:
    resolution = CapabilityCatalog((_contract(),), (_provider(),)).resolve(
        _requirements()
    )

    assert resolution.status == "eligible"
    assert resolution.unavailable == ()
    assert resolution.selected_provider_ids == ("private-test-provider",)


def test_catalog_uses_receiver_snapshot_order_for_deterministic_selection() -> None:
    primary = _provider()
    secondary = CapabilityProvider(
        "private-secondary-provider", _contract(), conformance_passed=True
    )

    resolution = CapabilityCatalog((_contract(),), (primary, secondary)).resolve(
        _requirements()
    )

    assert resolution.selected_provider_ids == ("private-test-provider",)


def test_catalog_revalidates_current_receiver_provider_availability() -> None:
    provider = _provider()
    states = [ProviderAvailability.AVAILABLE, ProviderAvailability.DISABLED]
    catalog = CapabilityCatalog(
        (_contract(),),
        (provider,),
        availability_provider=lambda _provider: states.pop(0),
    )

    resolution = catalog.resolve(_requirements())
    revalidation = catalog.revalidate(resolution.selected_provider_ids)

    assert resolution.status == "eligible"
    assert revalidation.status == "capability_unavailable"
    assert revalidation.unavailable == (
        UnavailableCapability("model.execution.test.v1", "disabled"),
    )


@pytest.mark.parametrize(
    ("provider", "expected_classification"),
    (
        (_provider(availability=ProviderAvailability.DISABLED), "disabled"),
        (
            _provider(availability=ProviderAvailability.PLATFORM_INCOMPATIBLE),
            "platform_incompatible",
        ),
        (
            _provider(availability=ProviderAvailability.OPTIONAL_COMPONENT_MISSING),
            "optional_component_missing",
        ),
        (_provider(conforms=False), None),
    ),
)
def test_catalog_redacts_unavailable_provider_details(
    provider: CapabilityProvider, expected_classification: str | None
) -> None:
    resolution = CapabilityCatalog((_contract(),), (provider,)).resolve(_requirements())

    assert resolution.status == "capability_unavailable"
    assert resolution.selected_provider_ids == ()
    assert resolution.unavailable[0].capability_id == "model.execution.test.v1"
    assert resolution.unavailable[0].classification == expected_classification
    assert "private-test-provider" not in repr(resolution.unavailable[0])


def test_catalog_rejects_contract_mismatch_and_empty_catalog() -> None:
    requirements = _requirements()

    mismatch = CapabilityCatalog(
        (CapabilityContract("model.execution.test.v1", "2", "b" * 64, ("image",)),),
        (),
    ).resolve(requirements)
    empty = CapabilityCatalog((), ()).resolve(requirements)

    assert mismatch.unavailable[0].classification is None
    assert empty.unavailable[0].classification is None


def test_catalog_revalidates_selected_provider_without_fallback() -> None:
    provider = _provider()
    catalog = CapabilityCatalog((_contract(),), (provider,))
    selected = catalog.resolve(_requirements()).selected_provider_ids

    unavailable = catalog.revalidate(
        selected, availability={"private-test-provider": ProviderAvailability.DISABLED}
    )

    assert unavailable.status == "capability_unavailable"
    assert unavailable.unavailable[0].classification == "disabled"


def test_builtin_contract_provider_requires_every_published_conformance_vector() -> (
    None
):
    contract = BUILTIN_CAPABILITY_CONTRACTS[0]
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement(
                contract.capability_id,
                contract.contract_version,
                contract.contract_digest,
                ("multimodal",),
            ),
        )
    )
    incomplete_provider = CapabilityProvider(
        "private-llama-provider",
        contract,
        conformance_passed=True,
        conformance_vector_ids=frozenset({"requested_features"}),
    )
    complete_provider = CapabilityProvider(
        "private-llama-provider",
        contract,
        conformance_passed=True,
        conformance_vector_ids=frozenset(
            {
                "requested_features",
                "output_integrity",
                "resource_limits",
                "redacted_failure",
            }
        ),
    )

    assert (
        CapabilityCatalog((contract,), (incomplete_provider,))
        .resolve(requirements)
        .status
        == "capability_unavailable"
    )
    assert (
        CapabilityCatalog((contract,), (complete_provider,))
        .resolve(requirements)
        .status
        == "eligible"
    )
