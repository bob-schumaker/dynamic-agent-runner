#!/usr/bin/env python3
"""Run one approved synthetic choice through one exact Jev-Style v3 profile."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
LEDGER_PATH = (
    ROOT
    / "specs/decision-model-support/evaluation/jevstyle-v3-dms17-profile-admission.json"
)
LEDGER = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
PREFLIGHT_PATH = (
    ROOT
    / "specs/decision-model-support/evaluation/preflight-jevstyle-v3-dms17-2026-10-03.json"
)
PROFILE_RECORDS: dict[str, dict[str, Any]] = LEDGER["profiles"]
RUNTIME_PROJECTS = {
    "mlx-metal": "jevstyle-mlx-runtime",
    "gguf-f16-cpu": "jevstyle-gguf-runtime",
    "torch-bf16-cpu": "jevstyle-torch-runtime",
}
MATERIAL_SUBDIRS = {
    "mlx-metal": Path("dms17-jevstyle-materials/mlx"),
    "gguf-f16-cpu": Path("dms01-additions/materials/jevstyle-gguf"),
    "torch-bf16-cpu": Path("dms01-additions/materials/jevstyle-torch"),
}
PROFILE_IDENTITIES = {
    "mlx-metal": "JEVSTYLE_V3_MLX_PROFILE",
    "gguf-f16-cpu": "JEVSTYLE_V3_GGUF_PROFILE",
    "torch-bf16-cpu": "JEVSTYLE_V3_TORCH_PROFILE",
}
SCOPE_FILES = (
    "tests/manual/smoke_jevstyle_dms17.py",
    "pyproject.toml",
    "src/dynamic_agent_runner/__init__.py",
    "src/dynamic_agent_runner/decision_models.py",
    "src/dynamic_agent_runner/workflow_host/jevstyle_decision_adapter.py",
    "src/dynamic_agent_runner/workflow_host/model_execution_binding.py",
    "src/dynamic_agent_runner/workflow_host/capabilities.py",
    "src/dynamic_agent_runner/workflow_host/execution_descriptors.py",
    "src/dynamic_agent_runner/workflow_host/model_materials.py",
    "specs/decision-model-support/evaluation/jevstyle-v3-dms17-profile-admission.json",
    "specs/decision-model-support/evaluation/jevstyle-mlx-runtime/pyproject.toml",
    "specs/decision-model-support/evaluation/jevstyle-mlx-runtime/poetry.lock",
    "specs/decision-model-support/evaluation/jevstyle-gguf-runtime/pyproject.toml",
    "specs/decision-model-support/evaluation/jevstyle-gguf-runtime/poetry.lock",
    "specs/decision-model-support/evaluation/jevstyle-torch-runtime/pyproject.toml",
    "specs/decision-model-support/evaluation/jevstyle-torch-runtime/poetry.lock",
)


class SmokeError(RuntimeError):
    """Raised when the exact DMS-17 smoke scope is not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def scope_payload(
    material_root: Path,
    scorer: Path,
    attempt: int = 1,
    profile_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if attempt < 1:
        raise SmokeError("attempt must be positive")
    selected_profiles = tuple(sorted(profile_ids or PROFILE_RECORDS))
    if not selected_profiles or any(
        profile_id not in PROFILE_RECORDS for profile_id in selected_profiles
    ):
        raise SmokeError("scope contains an unsupported profile")
    return {
        "action": "verify exact local files, stage only missing allowlisted files from the pinned revision, load offline through the Jev-Style selector, and make one synthetic choice request for each selected profile",
        "attempt": attempt,
        "selected_profiles": selected_profiles,
        "adapter_id": LEDGER["adapter_id"],
        "host": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "metal_available": platform.system() == "Darwin"
            and platform.machine().lower() in {"arm64", "aarch64"},
            "python": sys.version.split()[0],
            "resource_policy": "available free, inactive, and speculative pages must total at least twice the pinned DMS-01 peak RSS",
        },
        "materials": {
            name: {
                "model_id": record["model_id"],
                "model_revision": record["model_revision"],
                "expected_files": record["materials"]["files"],
                "runtime_lock_sha256": record["runtime"]["lock_sha256"],
                "material_path": str(_material_dir(material_root, name)),
            }
            for name, record in sorted(PROFILE_RECORDS.items())
            if name in selected_profiles
        },
        "scorer_path": str(scorer),
        "scorer_sha256": _sha256(scorer) if scorer.is_file() else None,
        "scope_files": {name: _sha256(ROOT / name) for name in SCOPE_FILES},
    }


def scope_digest(
    material_root: Path,
    scorer: Path,
    attempt: int = 1,
    profile_ids: tuple[str, ...] | None = None,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            scope_payload(material_root, scorer, attempt, profile_ids)
        )
    ).hexdigest()


def _verify_approval_receipt(
    scope: str, profile_id: str, profile_ids: tuple[str, ...]
) -> None:
    try:
        preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
        approval = preflight["approval"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as error:
        raise SmokeError("the DMS-17 approval receipt is absent or invalid") from error
    if not isinstance(preflight, dict) or not isinstance(approval, dict):
        raise SmokeError("the DMS-17 approval receipt is absent or invalid")
    if (
        preflight.get("run_allowed") is not True
        or preflight.get("profile_set_id") != LEDGER["profile_set_id"]
        or preflight.get("scope_sha256") != scope
        or approval.get("status") != "approved"
        or approval.get("scope_sha256") != scope
        or approval.get("profiles") != sorted(profile_ids)
        or profile_id not in approval["profiles"]
    ):
        raise SmokeError("the DMS-17 approval receipt does not authorize this profile")


def _receipt_path(profile_id: str, attempt: int = 1) -> Path:
    suffix = "" if attempt == 1 else f"-attempt-{attempt}"
    return (
        ROOT
        / "specs/decision-model-support/evaluation"
        / f"dms17-smoke-{profile_id}{suffix}.json"
    )


def _runtime_ready(profile_id: str) -> None:
    runtime = PROFILE_RECORDS[profile_id]["runtime"]
    project = (
        ROOT / "specs/decision-model-support/evaluation" / RUNTIME_PROJECTS[profile_id]
    )
    lock = project / "poetry.lock"
    if not lock.is_file() or _sha256(lock) != runtime["lock_sha256"]:
        raise SmokeError("the isolated runtime lock differs from its pinned digest")
    for package, expected in runtime["packages"].items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise SmokeError("the isolated backend runtime is not installed") from error
        if actual != expected:
            raise SmokeError("the installed backend runtime differs from its pin")


def _verify_materials(profile_id: str, material_dir: Path, scorer: Path) -> None:
    profile = PROFILE_RECORDS[profile_id]
    for name, expected in profile["materials"]["files"].items():
        path = material_dir / name
        if not path.is_file() or _sha256(path) != expected:
            raise SmokeError(
                f"pinned local model material is absent or changed: {name}"
            )
    if profile_id == "gguf-f16-cpu":
        expected = profile["materials"]["tested_scorer_binary_sha256"]
        if not scorer.is_file() or _sha256(scorer) != expected:
            raise SmokeError("the pinned GGUF scorer binary is absent or changed")


def _stage_exact_profile(profile_id: str, material_dir: Path) -> Path:
    profile = PROFILE_RECORDS[profile_id]
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=profile["model_id"],
            revision=profile["model_revision"],
            local_dir=str(material_dir),
            allow_patterns=list(profile["materials"]["files"]),
        )
    )


def _engine_loader(profile_id: str, material_dir: Path, scorer: Path) -> Any:
    sys.path.insert(0, str(material_dir))
    if profile_id == "mlx-metal":
        from jev_style_decision_mlx import JevStyleDecisionMLX

        return JevStyleDecisionMLX(
            material_dir, precision="8bit", verify=True, cache_limit_gib=2.0
        )
    if profile_id == "torch-bf16-cpu":
        from jev_style_decision import JevStyleDecision

        return JevStyleDecision(
            material_dir, device="cpu", dtype="bfloat16", verify=True
        )
    if profile_id == "gguf-f16-cpu":
        from jev_style_decision_gguf import JevStyleDecisionGGUF

        return JevStyleDecisionGGUF(
            material_dir,
            quant="F16",
            gguf=material_dir / "Jev-Style-0.8B-Decision-v3-F16.gguf",
            binary=scorer,
            n_gpu_layers=0,
            many_mode="exact",
            verify=True,
        )
    raise SmokeError("unsupported Jev-Style profile")


def _host_has_resource_budget(profile_id: str) -> bool:
    peak = PROFILE_RECORDS[profile_id]["observed_peak_rss_bytes"]
    if sys.platform == "darwin":
        output = subprocess.run(
            ["vm_stat"], check=True, capture_output=True, text=True
        ).stdout
        counts = [
            int(line.split(":", 1)[1].strip().replace(".", ""))
            for line in output.splitlines()
            if any(
                label in line
                for label in ("Pages free", "Pages inactive", "Pages speculative")
            )
        ]
        available = sum(counts) * os.sysconf("SC_PAGE_SIZE")
    else:
        available = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
    return available >= peak * 2


def run_profile(
    profile_id: str,
    material_root: Path,
    scorer: Path,
    approved_scope: str | None,
    *,
    attempt: int = 1,
    stage: Any | None = None,
    load: Any | None = None,
) -> dict[str, Any]:
    if profile_id not in PROFILE_RECORDS:
        raise SmokeError("unsupported Jev-Style profile")
    selected_profiles = (profile_id,)
    expected_scope = scope_digest(
        material_root, scorer, attempt, selected_profiles
    )
    if approved_scope != expected_scope:
        raise SmokeError(
            f"approval is absent or differs; required scope: {expected_scope}"
        )
    _verify_approval_receipt(expected_scope, profile_id, selected_profiles)
    receipt_path = _receipt_path(profile_id, attempt)
    if receipt_path.exists():
        raise SmokeError("a receipt already exists for this one-run profile approval")
    _runtime_ready(profile_id)
    material_dir = _material_dir(material_root, profile_id)
    if not _materials_present(profile_id, material_dir):
        material_dir = (stage or _stage_exact_profile)(profile_id, material_dir)
    _verify_materials(profile_id, material_dir, scorer)
    if not _host_has_resource_budget(profile_id):
        raise SmokeError("host does not have the admitted Jev-Style resource budget")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from dynamic_agent_runner.decision_models import (
        DecisionMode,
        DecisionModelRequest,
        DecisionOption,
        DecisionQuestion,
        validate_decision_result,
    )
    from dynamic_agent_runner.workflow_host import (
        jevstyle_decision_adapter as adapter_module,
    )
    from dynamic_agent_runner.workflow_host.model_execution_binding import (
        ModelExecutionBinding,
    )

    profile = getattr(adapter_module, PROFILE_IDENTITIES[profile_id])
    lock_digest = PROFILE_RECORDS[profile_id]["runtime"]["lock_sha256"]
    loaded_engines: list[Any] = []

    def load_selected(_binding: Any) -> Any:
        engine = (load or _engine_loader)(profile_id, material_dir, scorer)
        loaded_engines.append(engine)
        return engine

    candidate = adapter_module.JevStyleModelCandidate(
        backend=profile_id,
        profile=profile,
        execution_binding=ModelExecutionBinding(
            logical_model_id=profile.identity.model_id,
            runner_contract_id=f"{LEDGER['adapter_id']}.{profile_id}",
            runner_contract_version="1",
            loader_profile_contract_id=f"{LEDGER['adapter_id']}.{profile_id}.loader",
            loader_profile_contract_version="1",
            material_lock_digest=lock_digest,
            capability_requirements_digest=hashlib.sha256(
                _canonical_json(PROFILE_RECORDS[profile_id]["materials"]["files"])
            ).hexdigest(),
            runner_capability_id=f"{LEDGER['adapter_id']}.{profile_id}.runner",
            runner_capability_version="1",
            runner_capability_digest=hashlib.sha256(lock_digest.encode()).hexdigest(),
        ),
        materials_admitted=True,
        resource_admitted=True,
        load_engine=load_selected,
    )
    machine_name = platform.system().lower()
    machine = adapter_module.JevStyleMachineConfiguration(
        "darwin"
        if machine_name == "darwin"
        else "win32"
        if machine_name == "windows"
        else "linux",
        platform.machine().lower(),
        machine_name == "darwin" and platform.machine().lower() in {"arm64", "aarch64"},
    )
    binding = adapter_module.load_jevstyle_v3_binding(machine, (candidate,))
    request = DecisionModelRequest(
        decision_id="dms17-synthetic-smoke",
        context="A customer reports a duplicate charge and asks for help.",
        questions=(
            DecisionQuestion(
                id="route",
                text="Which team should handle this request?",
                options=(
                    DecisionOption("billing", "Billing"),
                    DecisionOption("other", "Other support"),
                ),
            ),
        ),
        mode=DecisionMode.CHOICE,
    )
    started = time.perf_counter()
    result = binding.adapter.decide(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    validate_decision_result(result, request, binding.profile)
    if result.results[0].choice not in {"billing", "other"}:
        raise SmokeError(
            "the Jev-Style smoke result is not one of the supplied options"
        )
    engine = loaded_engines[0]
    close = getattr(engine, "close", None)
    if callable(close):
        close()
    report = {
        "approval_scope": expected_scope,
        "adapter_id": LEDGER["adapter_id"],
        "profile_id": profile_id,
        "model_id": profile.identity.model_id,
        "model_revision": profile.identity.model_revision,
        "runtime_lock_sha256": lock_digest,
        "material_file_count": len(PROFILE_RECORDS[profile_id]["materials"]["files"]),
        "selected_profile_id": binding.profile.identity.profile_id,
        "inference_count": 1,
        "result_valid": True,
        "elapsed_ms": elapsed_ms,
        "choice": result.results[0].choice,
        "network_disabled_before_load": True,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _materials_present(profile_id: str, material_dir: Path) -> bool:
    return all(
        (material_dir / name).is_file()
        for name in PROFILE_RECORDS[profile_id]["materials"]["files"]
    )


def _material_dir(material_root: Path, profile_id: str) -> Path:
    return material_root / MATERIAL_SUBDIRS[profile_id]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILE_RECORDS))
    parser.add_argument("--material-root", type=Path, default=Path("/private/tmp"))
    parser.add_argument(
        "--scorer", type=Path, default=Path("/private/tmp/dms01-additions/jev-score")
    )
    parser.add_argument("--approved-scope")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--show-scope", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.show_scope:
        profile_ids = (args.profile,) if args.profile else None
        print(
            scope_digest(
                args.material_root, args.scorer, args.attempt, profile_ids
            )
        )
        return 0
    if args.profile is None:
        raise SmokeError("--profile is required for an approved smoke")
    print(
        json.dumps(
            run_profile(
                args.profile,
                args.material_root,
                args.scorer,
                args.approved_scope,
                attempt=args.attempt,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
