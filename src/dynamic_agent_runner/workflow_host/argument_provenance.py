"""Verification for model-facing v1 tool-argument provenance envelopes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field


class ArgumentProvenanceError(ValueError):
    """Raised when a model tool argument has no approved, reproducible source."""


@dataclass(frozen=True)
class ArgumentSourcePolicy:
    """Allowed proof kinds for one argument and whether it conveys authority."""

    allowed_kinds: frozenset[str]
    authority_field: bool
    allowed_references: Mapping[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ArgumentVerificationContext:
    """Wrapper-private materials against which one envelope is checked."""

    original_prompt: str
    sealed_fields: Mapping[str, object]
    artifact_values: Mapping[str, object]
    constants: Mapping[str, object]
    argument_policies: Mapping[str, ArgumentSourcePolicy]


def verify_argument_provenance(
    serialized: str, context: ArgumentVerificationContext
) -> dict[str, object]:
    """Return verified normalized arguments, never provenance metadata.

    The caller supplies the original sealed prompt and opaque reference maps;
    envelopes cannot introduce source material or authority-bearing transforms.
    """

    envelope = _parse_canonical_envelope(serialized)
    arguments = _object(envelope.get("arguments"), "arguments")
    sources = _object(envelope.get("sources"), "sources")
    if set(envelope) != {"format_version", "arguments", "sources"}:
        raise ArgumentProvenanceError("envelope fields are invalid")
    if envelope["format_version"] != 1:
        raise ArgumentProvenanceError("envelope format_version is invalid")
    if not arguments or set(arguments) != set(sources):
        raise ArgumentProvenanceError("argument source proofs are incomplete")
    if set(arguments) != set(context.argument_policies):
        raise ArgumentProvenanceError("envelope arguments do not match policy")

    verified: dict[str, object] = {}
    for name, value in arguments.items():
        if not isinstance(name, str) or not name:
            raise ArgumentProvenanceError("argument name is invalid")
        policy = context.argument_policies[name]
        _verify_source(value, _object(sources[name], "source proof"), policy, context)
        verified[name] = value
    return verified


def _parse_canonical_envelope(serialized: str) -> dict[str, object]:
    if not isinstance(serialized, str):
        raise ArgumentProvenanceError("envelope must be JSON text")
    try:
        encoded = serialized.encode("utf-8")
        decoded = json.loads(
            serialized,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ArgumentProvenanceError("envelope is not valid UTF-8 JSON") from error
    if not isinstance(decoded, dict):
        raise ArgumentProvenanceError("envelope must be a JSON object")
    canonical = json.dumps(
        decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if encoded != canonical:
        raise ArgumentProvenanceError("envelope JSON is not canonical")
    return decoded


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _verify_source(
    value: object,
    proof: dict[str, object],
    policy: ArgumentSourcePolicy,
    context: ArgumentVerificationContext,
) -> None:
    kind = proof.get("kind")
    if not isinstance(kind, str) or kind not in policy.allowed_kinds:
        raise ArgumentProvenanceError("argument source kind is not permitted")
    if kind == "prompt_span":
        _verify_prompt_span(value, proof, context.original_prompt)
        return
    if kind in {"sealed_field", "artifact", "constant"}:
        _verify_opaque_reference(value, proof, kind, context, policy)
        return
    if kind == "compose_content_v1":
        _verify_compose_content(value, proof, policy, context)
        return
    raise ArgumentProvenanceError("argument source kind is invalid")


def _verify_prompt_span(value: object, proof: dict[str, object], prompt: str) -> None:
    if set(proof) != {"kind", "start_byte", "end_byte", "normalization"}:
        raise ArgumentProvenanceError("prompt span proof is invalid")
    start = proof["start_byte"]
    end = proof["end_byte"]
    normalization = proof["normalization"]
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or not isinstance(normalization, str)
    ):
        raise ArgumentProvenanceError("prompt span proof is invalid")
    encoded_prompt = prompt.encode("utf-8")
    if end > len(encoded_prompt):
        raise ArgumentProvenanceError("prompt span is outside the sealed prompt")
    try:
        selected = encoded_prompt[start:end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArgumentProvenanceError("prompt span is not UTF-8 aligned") from error
    normalized = _normalize(selected, normalization)
    if value != normalized:
        raise ArgumentProvenanceError("prompt span does not reconstruct argument")


def _normalize(value: str, normalization: str) -> str:
    if normalization == "identity":
        return value
    if normalization == "trim_ascii_whitespace":
        return value.strip(" \t\r\n\v\f")
    raise ArgumentProvenanceError("prompt normalization is not registered")


def _verify_opaque_reference(
    value: object,
    proof: dict[str, object],
    kind: str,
    context: ArgumentVerificationContext,
    policy: ArgumentSourcePolicy | None = None,
) -> None:
    if set(proof) != {"kind", "ref"} or not isinstance(proof.get("ref"), str):
        raise ArgumentProvenanceError("opaque source reference is invalid")
    reference = proof["ref"]
    if (
        policy is not None
        and policy.allowed_references
        and reference not in policy.allowed_references.get(kind, frozenset())
    ):
        raise ArgumentProvenanceError("opaque source reference is not permitted")
    references = {
        "sealed_field": context.sealed_fields,
        "artifact": context.artifact_values,
        "constant": context.constants,
    }[kind]
    try:
        resolved = references[reference]
    except KeyError as error:
        raise ArgumentProvenanceError(
            "opaque source reference is unavailable"
        ) from error
    if value != resolved:
        raise ArgumentProvenanceError("opaque source does not reconstruct argument")


def _verify_compose_content(
    value: object,
    proof: dict[str, object],
    policy: ArgumentSourcePolicy,
    context: ArgumentVerificationContext,
) -> None:
    if policy.authority_field:
        raise ArgumentProvenanceError(
            "model-generated content cannot supply an authority field"
        )
    if not isinstance(value, str) or set(proof) != {"kind", "inputs"}:
        raise ArgumentProvenanceError("content transform proof is invalid")
    inputs = proof["inputs"]
    if not isinstance(inputs, list) or not 0 < len(inputs) <= 8:
        raise ArgumentProvenanceError("content transform inputs are invalid")
    for item in inputs:
        reference = _object(item, "transform input")
        kind = reference.get("kind")
        if kind not in {"sealed_field", "artifact", "constant"}:
            raise ArgumentProvenanceError("transform input is not permitted")
        _verify_opaque_reference(
            {
                "sealed_field": context.sealed_fields,
                "artifact": context.artifact_values,
                "constant": context.constants,
            }[kind].get(reference.get("ref")),
            reference,
            kind,
            context,
            policy,
        )


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ArgumentProvenanceError(f"{label} must be an object")
    return value
