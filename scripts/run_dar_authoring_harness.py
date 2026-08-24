#!/usr/bin/env python3
"""Run one private DAR authoring fixture through an external generator."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Any, Sequence

import yaml

from dynamic_agent_runner.workflow_host.authoring_evidence import (
    AuthoringEvidence,
    ExternalAuthoringHarnessRequest,
    ValidatingExternalAuthoringHarness,
    write_authoring_evidence,
)
from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialProjectionMember,
    AuthoringMaterialSetProjection,
)


class HarnessError(ValueError):
    """Raised when an external authoring harness input or output is invalid."""


def run_fixture(
    *,
    fixture_path: Path,
    materials_path: Path,
    generator: Sequence[str],
    provider: str,
    model_id: str,
    reviewer_decision: str,
    evidence_path: Path,
    pass_criteria: Sequence[str],
    timeout: float,
    host_package_root: Path | None = None,
    host_package_name: str | None = None,
) -> dict[str, object]:
    """Run one generator privately and persist only its redacted evidence."""

    fixture_bytes = _read_bytes(fixture_path, "fixture")
    fixture = _fixture(json.loads(_decode(fixture_bytes, "fixture")))
    materials = _materials(
        json.loads(_decode(_read_bytes(materials_path, "materials"), "materials")),
        fixture["selected_materials"],
    )
    request = ExternalAuthoringHarnessRequest(
        skill_name=fixture["skill"], request=fixture["request"], materials=materials
    )
    outcome = _run_generator(
        request=request,
        expected_artifacts=fixture["expected_artifacts"],
        artifact_contracts=fixture["artifact_contracts"],
        generator=generator,
        timeout=timeout,
        host_package_root=host_package_root,
        host_package_name=host_package_name,
    )
    _validate_review(reviewer_decision, outcome.validator_result)
    evidence = AuthoringEvidence(
        corpus_digest=hashlib.sha256(fixture_bytes).hexdigest(),
        prompt_digest=hashlib.sha256(request.request.encode("utf-8")).hexdigest(),
        material_set_id=materials.material_set_id,
        authoring_provider=_text(provider, "provider"),
        authoring_model_id=_text(model_id, "model_id"),
        generated_package_digests=outcome.generated_package_digests,
        validator_result=outcome.validator_result,
        reviewer_decision=reviewer_decision,
        pass_criteria=_criteria(pass_criteria),
        retention_policy="redacted-evidence-v1",
    )
    write_authoring_evidence(evidence_path, evidence)
    return evidence.to_mapping()


def _run_generator(
    *,
    request: ExternalAuthoringHarnessRequest,
    expected_artifacts: tuple[str, ...],
    artifact_contracts: tuple[dict[str, object], ...],
    generator: Sequence[str],
    timeout: float,
    host_package_root: Path | None,
    host_package_name: str | None,
):
    if not generator or any(
        not isinstance(item, str) or not item for item in generator
    ):
        raise HarnessError("generator command is invalid")
    if timeout <= 0:
        raise HarnessError("generator timeout is invalid")
    with tempfile.TemporaryDirectory(prefix="dar-authoring-harness-") as directory:
        root = Path(directory)
        request_path = root / "request.json"
        output_path = _output_path(
            temporary_root=root,
            host_package_root=host_package_root,
            host_package_name=host_package_name,
        )
        _write_private_request(request_path, request)
        try:
            result = subprocess.run(
                [
                    *generator,
                    "--request",
                    str(request_path),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return _failed_outcome()
        if result.returncode:
            return _failed_outcome()
        if not _expected_artifacts_exist(output_path, expected_artifacts):
            return _failed_outcome()
        if not _artifact_contracts_hold(output_path, artifact_contracts):
            return _failed_outcome()

        class Generator:
            def generate(self, _request: ExternalAuthoringHarnessRequest) -> Path:
                return output_path

        return ValidatingExternalAuthoringHarness(Generator()).run(request)


def _output_path(
    *,
    temporary_root: Path,
    host_package_root: Path | None,
    host_package_name: str | None,
) -> Path:
    if host_package_root is None and host_package_name is None:
        output_path = temporary_root / "output"
        output_path.mkdir(mode=0o700)
        return output_path
    if host_package_root is None or host_package_name is None:
        raise HarnessError(
            "host package root and host package name must be supplied together"
        )
    if (
        not host_package_root.is_absolute()
        or "." in host_package_root.parts
        or ".." in host_package_root.parts
    ):
        raise HarnessError("host package root is invalid")
    try:
        mode = os.lstat(host_package_root).st_mode
    except OSError as error:
        raise HarnessError("host package root is unavailable") from error
    if not stat.S_ISDIR(mode) or os.path.islink(host_package_root):
        raise HarnessError("host package root is unavailable")
    if (
        not host_package_name
        or len(host_package_name) > 64
        or host_package_name.startswith(".")
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in host_package_name
        )
    ):
        raise HarnessError("host package name is invalid")
    output_path = host_package_root / host_package_name
    if output_path.exists() or output_path.is_symlink():
        raise HarnessError("host package output already exists")
    return output_path


def _write_private_request(
    destination: Path, request: ExternalAuthoringHarnessRequest
) -> None:
    value = {
        "format_version": 1,
        "skill": request.skill_name,
        "request": request.request,
        "materials": {
            "material_set_id": request.materials.material_set_id,
            "members": [
                {
                    "artifact_id": member.artifact_id,
                    "content": member.content,
                    "digest": member.digest,
                    "disposition": member.disposition,
                    "role": member.role,
                }
                for member in request.materials.members
            ],
        },
    }
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, json.dumps(value, sort_keys=True).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _expected_artifacts_exist(root: Path, expected: tuple[str, ...]) -> bool:
    return all(
        path.is_file() and not path.is_symlink()
        for path in (root / relative_path for relative_path in expected)
    )


def _artifact_contracts_hold(
    root: Path, contracts: Sequence[dict[str, object]]
) -> bool:
    for contract in contracts:
        artifact = contract["artifact"]
        assert isinstance(artifact, str)
        try:
            content = (root / artifact).read_text(encoding="utf-8")
        except OSError:
            return False
        forbidden_text = contract["forbidden_text"]
        assert isinstance(forbidden_text, tuple)
        if any(text in content for text in forbidden_text):
            return False
        try:
            value = (
                json.loads(content)
                if contract["format"] == "json"
                else yaml.safe_load(content)
            )
        except (json.JSONDecodeError, yaml.YAMLError):
            return False
        required = contract["required"]
        assert isinstance(required, dict)
        if not _contains_mapping(value, required):
            return False
    return True


def _contains_mapping(value: object, required: dict[str, object]) -> bool:
    if not isinstance(value, dict):
        return False
    for key, expected in required.items():
        actual = value.get(key)
        if isinstance(expected, dict):
            if not _contains_mapping(actual, expected):
                return False
        elif actual != expected:
            return False
    return True


def _fixture(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "artifact_contracts",
        "expected_artifacts",
        "expected_capability_or_refusal",
        "private_material_exclusions",
        "request",
        "schema_version",
        "selected_materials",
        "skill",
    }:
        raise HarnessError("fixture is invalid")
    if value["schema_version"] != 1:
        raise HarnessError("fixture schema version is invalid")
    _text(value["skill"], "fixture skill")
    _text(value["request"], "fixture request")
    artifacts = value["expected_artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise HarnessError("fixture artifacts are invalid")
    if any(not _safe_relative_path(item) for item in artifacts):
        raise HarnessError("fixture artifacts are invalid")
    contracts = _artifact_contracts(value["artifact_contracts"], artifacts)
    materials = value["selected_materials"]
    if not isinstance(materials, list) or not materials:
        raise HarnessError("fixture materials are invalid")
    _fixture_materials(materials)
    return {
        "artifact_contracts": contracts,
        "expected_artifacts": tuple(artifacts),
        "request": value["request"],
        "selected_materials": materials,
        "skill": value["skill"],
    }


def _artifact_contracts(
    value: object, artifacts: Sequence[str]
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not value:
        raise HarnessError("fixture artifact contracts are invalid")
    contracts: list[dict[str, object]] = []
    for contract in value:
        if (
            not isinstance(contract, dict)
            or not {
                "artifact",
                "format",
                "required",
            }
            <= set(contract)
            or set(contract)
            - {
                "artifact",
                "format",
                "required",
                "forbidden_text",
            }
        ):
            raise HarnessError("fixture artifact contracts are invalid")
        artifact = contract["artifact"]
        if not isinstance(artifact, str) or artifact not in artifacts:
            raise HarnessError("fixture artifact contracts are invalid")
        format_name = contract["format"]
        if format_name not in {"json", "yaml"}:
            raise HarnessError("fixture artifact contracts are invalid")
        required = contract["required"]
        if not isinstance(required, dict) or not _contract_value(required):
            raise HarnessError("fixture artifact contracts are invalid")
        forbidden_text = contract.get("forbidden_text", [])
        if not isinstance(forbidden_text, list) or any(
            not isinstance(text, str) or not text for text in forbidden_text
        ):
            raise HarnessError("fixture artifact contracts are invalid")
        contracts.append(
            {
                "artifact": artifact,
                "format": format_name,
                "forbidden_text": tuple(forbidden_text),
                "required": required,
            }
        )
    return tuple(contracts)


def _contract_value(value: object) -> bool:
    if isinstance(value, dict):
        return bool(value) and all(
            isinstance(key, str) and key and _contract_value(member)
            for key, member in value.items()
        )
    if isinstance(value, list):
        return all(_contract_value(member) for member in value)
    return value is None or isinstance(value, str | int | float | bool)


def _materials(
    value: object, selected: Sequence[dict[str, object]]
) -> AuthoringMaterialSetProjection:
    if not isinstance(value, dict) or set(value) != {
        "expires_at",
        "material_set_id",
        "members",
    }:
        raise HarnessError("materials are invalid")
    material_set_id = _text(value["material_set_id"], "material set id")
    try:
        expires_at = datetime.fromisoformat(_text(value["expires_at"], "expiry"))
    except ValueError as error:
        raise HarnessError("materials expiry is invalid") from error
    members = value["members"]
    if not isinstance(members, list) or len(members) != len(selected):
        raise HarnessError("materials are invalid")
    projection: list[AuthoringMaterialProjectionMember] = []
    for supplied, expected in zip(members, selected, strict=True):
        if not isinstance(supplied, dict) or set(supplied) != {
            "artifact_id",
            "content",
            "digest",
            "disposition",
            "role",
        }:
            raise HarnessError("materials are invalid")
        if any(supplied[key] != expected[key] for key in expected):
            raise HarnessError("materials do not match fixture")
        projection.append(
            AuthoringMaterialProjectionMember(
                artifact_id=_text(supplied["artifact_id"], "artifact id"),
                digest=_digest(supplied["digest"], "material digest"),
                role=_text(supplied["role"], "material role"),
                disposition=_disposition(supplied["disposition"]),
                content=_text(supplied["content"], "material content"),
            )
        )
    return AuthoringMaterialSetProjection(
        material_set_id=material_set_id,
        members=tuple(projection),
        expires_at=expires_at,
    )


def _fixture_materials(materials: Sequence[object]) -> None:
    for material in materials:
        if not isinstance(material, dict) or set(material) != {
            "artifact_id",
            "digest",
            "disposition",
            "role",
        }:
            raise HarnessError("fixture materials are invalid")
        _text(material["artifact_id"], "artifact id")
        _digest(material["digest"], "material digest")
        _text(material["role"], "material role")
        _disposition(material["disposition"])


def _validate_review(decision: str, result: str) -> None:
    if decision not in {"approved", "rejected"}:
        raise HarnessError("reviewer decision is invalid")
    if (result == "passed") != (decision == "approved"):
        raise HarnessError("reviewer decision does not match validator result")


def _criteria(values: Sequence[str]) -> tuple[str, ...]:
    criteria = tuple(_text(value, "pass criterion") for value in values)
    if not criteria:
        raise HarnessError("pass criteria are invalid")
    return criteria


def _failed_outcome():
    return ValidatingExternalAuthoringHarness(_FailingGenerator()).run(
        ExternalAuthoringHarnessRequest(
            skill_name="failed", request="failed", materials=_empty_materials()
        )
    )


class _FailingGenerator:
    def generate(self, _request: ExternalAuthoringHarnessRequest) -> Path:
        raise HarnessError("external generator failed")


def _empty_materials() -> AuthoringMaterialSetProjection:
    return AuthoringMaterialSetProjection(
        material_set_id="failed", members=(), expires_at=datetime.fromtimestamp(0)
    )


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise HarnessError(f"{label} is unavailable") from error


def _decode(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessError(f"{label} is not UTF-8") from error


def _safe_relative_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and all(part not in {"", ".", ".."} for part in Path(value).parts)
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise HarnessError(f"{label} is invalid")
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise HarnessError(f"{label} is invalid")
    return value


def _disposition(value: object) -> str:
    if value not in {"reference_only", "distributable"}:
        raise HarnessError("material disposition is invalid")
    assert isinstance(value, str)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", dest="fixture_path", required=True, type=Path)
    parser.add_argument("--materials", dest="materials_path", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--reviewer-decision", required=True)
    parser.add_argument("--evidence", dest="evidence_path", required=True, type=Path)
    parser.add_argument(
        "--pass-criterion", dest="pass_criteria", action="append", default=[]
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--host-package-root",
        type=Path,
        help="configured DAR package root for a control-plane authored package",
    )
    parser.add_argument(
        "--host-package-name",
        help="new configured-root package name for a control-plane authored package",
    )
    parser.add_argument("--generator", nargs=argparse.REMAINDER, required=True)
    arguments = parser.parse_args()
    try:
        print(json.dumps(run_fixture(**vars(arguments)), sort_keys=True))
    except (HarnessError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
