"""RED contract vectors for the sealed artifact runner descriptor."""

from __future__ import annotations

import hashlib
import json

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactRunnerDescriptorError,
    parse_sealed_artifact_runner_descriptor,
    verify_sealed_artifact_runner_files,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _descriptor() -> dict[str, object]:
    value: dict[str, object] = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/example.py",
            "sha256": "a" * 64,
        },
        "callbacks": [],
        "capability_requirements_digest": "b" * 64,
        "child_contract_digests": [],
        "format_version": 1,
        "inputs": [],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 1,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 1,
        },
        "outputs": [
            {
                "max_bytes": 1,
                "media_type": "application/octet-stream",
                "role": "result",
                "schema_digest": None,
            }
        ],
        "profile_digest": "c" * 64,
        "schemas": [],
    }
    value["artifact_runner_digest"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def test_parser_accepts_the_normative_v1_canonicalization_vector() -> None:
    descriptor = _descriptor()

    parsed = parse_sealed_artifact_runner_descriptor(_canonical(descriptor))

    assert (
        parsed.digest
        == "2c3ed7f8dc3c1aefe51d97bfc699bb7de6c5c5239a6b7a0df025acbf2ebb13f4"
    )
    assert descriptor["artifact_runner_digest"] == parsed.digest
    assert parsed.asset_path == "assets/example.py"
    assert parsed.output_roles == ("result",)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda value: value.__setitem__("unknown", "value"),
            "descriptor is invalid",
        ),
        (
            lambda value: value["asset"].__setitem__("entrypoint", "other"),
            "descriptor is invalid",
        ),
        (
            lambda value: value["asset"].__setitem__("path", "assets/example.txt"),
            "descriptor is invalid",
        ),
        (
            lambda value: value["outputs"].__setitem__(
                0,
                {
                    "max_bytes": 1,
                    "media_type": "application/json",
                    "role": "Result",
                    "schema_digest": None,
                },
            ),
            "descriptor is invalid",
        ),
        (
            lambda value: value["limits"].__setitem__("max_io_bytes", True),
            "descriptor is invalid",
        ),
        (
            lambda value: value.__setitem__("artifact_runner_digest", "0" * 64),
            "descriptor digest does not match",
        ),
    ],
)
def test_parser_rejects_noncanonical_v1_contracts(mutate, expected: str) -> None:
    descriptor = _descriptor()
    mutate(descriptor)
    if expected == "descriptor is invalid":
        unsigned = dict(descriptor)
        del unsigned["artifact_runner_digest"]
        descriptor["artifact_runner_digest"] = hashlib.sha256(
            _canonical(unsigned)
        ).hexdigest()

    with pytest.raises(SealedArtifactRunnerDescriptorError, match=expected):
        parse_sealed_artifact_runner_descriptor(_canonical(descriptor))


def test_parser_rejects_duplicate_json_keys_before_descriptor_processing() -> None:
    value = _canonical(_descriptor()).decode("utf-8")
    duplicate = value.replace(
        '"format_version":1', '"format_version":1,"format_version":1'
    )

    with pytest.raises(SealedArtifactRunnerDescriptorError, match="duplicate"):
        parse_sealed_artifact_runner_descriptor(duplicate.encode("utf-8"))


@pytest.mark.parametrize(
    "encoded",
    [
        lambda value: b"\xef\xbb\xbf" + value,
        lambda value: value + b"\n",
        lambda value: value.replace(b'":', b'": ', 1),
        lambda value: value.replace(
            b'"abi_version":1', b'"abi_version":1,"abi_version":1'
        ),
    ],
)
def test_parser_rejects_noncanonical_descriptor_bytes(encoded) -> None:
    with pytest.raises(SealedArtifactRunnerDescriptorError):
        parse_sealed_artifact_runner_descriptor(encoded(_canonical(_descriptor())))


def test_verifier_rejects_invalid_or_tampered_declared_schema(tmp_path) -> None:
    asset = b"def run(context):\n    return None\n"
    schema = b'{"type":"object"}'
    descriptor = _descriptor()
    descriptor["asset"]["sha256"] = hashlib.sha256(asset).hexdigest()
    descriptor["schemas"] = [
        {
            "dialect": "json-schema-draft-2020-12",
            "path": "schemas/result.json",
            "sha256": hashlib.sha256(schema).hexdigest(),
        }
    ]
    descriptor["outputs"][0] = {
        "max_bytes": 1,
        "media_type": "application/json",
        "role": "result",
        "schema_digest": hashlib.sha256(schema).hexdigest(),
    }
    unsigned = dict(descriptor)
    del unsigned["artifact_runner_digest"]
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        _canonical(unsigned)
    ).hexdigest()
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "example.py").write_bytes(asset)
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "result.json").write_bytes(schema)

    verify_sealed_artifact_runner_files(tmp_path, _canonical(descriptor))

    (tmp_path / "schemas" / "result.json").write_bytes(b"not json")
    with pytest.raises(SealedArtifactRunnerDescriptorError):
        verify_sealed_artifact_runner_files(tmp_path, _canonical(descriptor))

    invalid_schema = b"not json"
    descriptor["schemas"][0]["sha256"] = hashlib.sha256(invalid_schema).hexdigest()
    descriptor["outputs"][0]["schema_digest"] = hashlib.sha256(
        invalid_schema
    ).hexdigest()
    unsigned = dict(descriptor)
    del unsigned["artifact_runner_digest"]
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        _canonical(unsigned)
    ).hexdigest()
    with pytest.raises(SealedArtifactRunnerDescriptorError):
        verify_sealed_artifact_runner_files(tmp_path, _canonical(descriptor))
