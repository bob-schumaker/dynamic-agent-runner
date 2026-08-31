"""Tests for v1 tool-argument provenance envelopes."""

from __future__ import annotations

import json

import pytest


from dynamic_agent_runner.workflow_host.argument_provenance import (  # noqa: E402
    ArgumentProvenanceError,
    ArgumentSourcePolicy,
    ArgumentVerificationContext,
    verify_argument_provenance,
)


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _context(
    *,
    prompt: str = "Send to José.",
    policies: dict[str, ArgumentSourcePolicy] | None = None,
) -> ArgumentVerificationContext:
    return ArgumentVerificationContext(
        original_prompt=prompt,
        sealed_fields={"recipient": "jose@example.test"},
        artifact_values={"v1.body": "<p>Hello</p>"},
        constants={"default_subject": "Welcome"},
        argument_policies=policies
        or {
            "recipient": ArgumentSourcePolicy(frozenset({"sealed_field"}), True),
            "subject": ArgumentSourcePolicy(frozenset({"prompt_span"}), True),
            "body": ArgumentSourcePolicy(
                frozenset({"artifact", "compose_content_v1"}), False
            ),
        },
    )


def test_verifier_reconstructs_utf8_prompt_spans_and_opaque_references() -> None:
    prompt = "Send to José."
    subject = "José"
    start = prompt.encode("utf-8").index(subject.encode("utf-8"))
    end = start + len(subject.encode("utf-8"))
    envelope = {
        "format_version": 1,
        "arguments": {
            "recipient": "jose@example.test",
            "subject": subject,
            "body": "<p>Hello</p>",
        },
        "sources": {
            "recipient": {"kind": "sealed_field", "ref": "recipient"},
            "subject": {
                "kind": "prompt_span",
                "start_byte": start,
                "end_byte": end,
                "normalization": "identity",
            },
            "body": {"kind": "artifact", "ref": "v1.body"},
        },
    }

    verified = verify_argument_provenance(_canonical(envelope), _context(prompt=prompt))

    assert verified == envelope["arguments"]


def test_verifier_rejects_noncanonical_json_and_non_utf8_span_boundaries() -> None:
    envelope = {
        "format_version": 1,
        "arguments": {"subject": "José"},
        "sources": {
            "subject": {
                "kind": "prompt_span",
                "start_byte": 11,
                "end_byte": 12,
                "normalization": "identity",
            }
        },
    }
    context = _context(
        policies={"subject": ArgumentSourcePolicy(frozenset({"prompt_span"}), True)}
    )

    with pytest.raises(ArgumentProvenanceError, match="canonical"):
        verify_argument_provenance(json.dumps(envelope), context)
    with pytest.raises(ArgumentProvenanceError, match="span"):
        verify_argument_provenance(_canonical(envelope), context)


def test_verifier_accepts_registered_trim_ascii_whitespace_normalization() -> None:
    prompt = "Subject:  Welcome \t"
    value = "Welcome"
    start = len("Subject:".encode("utf-8"))
    envelope = {
        "format_version": 1,
        "arguments": {"subject": value},
        "sources": {
            "subject": {
                "kind": "prompt_span",
                "start_byte": start,
                "end_byte": len(prompt.encode("utf-8")),
                "normalization": "trim_ascii_whitespace",
            }
        },
    }
    context = _context(
        prompt=prompt,
        policies={"subject": ArgumentSourcePolicy(frozenset({"prompt_span"}), True)},
    )

    assert verify_argument_provenance(_canonical(envelope), context) == {
        "subject": value
    }


@pytest.mark.parametrize("forbidden_kind", ["remote_output", "additional_context"])
def test_verifier_rejects_laundering_into_model_generated_content(
    forbidden_kind: str,
) -> None:
    envelope = {
        "format_version": 1,
        "arguments": {"body": "Generated text"},
        "sources": {
            "body": {
                "kind": "compose_content_v1",
                "inputs": [{"kind": forbidden_kind, "ref": "untrusted"}],
            }
        },
    }
    context = _context(
        policies={
            "body": ArgumentSourcePolicy(frozenset({"compose_content_v1"}), False)
        }
    )

    with pytest.raises(ArgumentProvenanceError, match="transform input"):
        verify_argument_provenance(_canonical(envelope), context)


def test_verifier_rejects_model_generated_content_for_an_authority_field() -> None:
    envelope = {
        "format_version": 1,
        "arguments": {"recipient": "attacker@example.test"},
        "sources": {
            "recipient": {
                "kind": "compose_content_v1",
                "inputs": [{"kind": "constant", "ref": "default_subject"}],
            }
        },
    }
    context = _context(
        policies={
            "recipient": ArgumentSourcePolicy(frozenset({"compose_content_v1"}), True)
        }
    )

    with pytest.raises(ArgumentProvenanceError, match="authority"):
        verify_argument_provenance(_canonical(envelope), context)
