#!/usr/bin/env python3
"""Run one approved, synthetic, offline-after-staging DMS-16 smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import preflight_dms16 as preflight  # noqa: E402

from dynamic_agent_runner.decision_models import (  # noqa: E402
    DecisionMode,
    DecisionModelProfile,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionOption,
    DecisionQuestion,
    validate_decision_result,
)
from dynamic_agent_runner.workflow_host.julia1_decision_adapter import (  # noqa: E402
    JULIA1_DECISION_IDENTITY,
    Julia1DecisionAdapter,
)
from dynamic_agent_runner.workflow_host.laya_mlx_decision_adapter import (  # noqa: E402
    LAYA_MLX_DECISION_IDENTITY,
    LayaMLXDecisionAdapter,
)
from dynamic_agent_runner.workflow_host.von_decision_adapter import (  # noqa: E402
    VON_DECISION_IDENTITY,
    VonDecisionAdapter,
)

POETRY_LOCK_SHA256 = preflight.POETRY_LOCK_SHA256
PROFILE_MANIFESTS = {
    name: {
        "model_id": profile["model_id"],
        "model_revision": profile["model_revision"],
        "source_revision": profile["source_revision"],
        "files": profile["files"],
        "git_files": profile.get("git_files", {}),
        "packages": profile["packages"],
    }
    for name, profile in preflight.PROFILES.items()
}
IDENTITIES = {
    "von": VON_DECISION_IDENTITY,
    "julia1": JULIA1_DECISION_IDENTITY,
    "laya-mlx": LAYA_MLX_DECISION_IDENTITY,
}
SCOPE_FILES = (
    "tests/manual/smoke_dms16.py",
    "tests/manual/preflight_dms16.py",
    "pyproject.toml",
    "src/dynamic_agent_runner/decision_models.py",
    "src/dynamic_agent_runner/workflow_host/von_decision_adapter.py",
    "src/dynamic_agent_runner/workflow_host/julia1_decision_adapter.py",
    "src/dynamic_agent_runner/workflow_host/laya_mlx_decision_adapter.py",
)
_SYNTHETIC_STATE = "A customer reports a duplicate charge and asks for help."
_SYNTHETIC_QUESTION = "Which team should handle this request?"
_SYNTHETIC_OPTIONS = (
    DecisionOption("billing", "Billing"),
    DecisionOption("access", "Account access"),
    DecisionOption("other", "Other support"),
)


class SmokeError(RuntimeError):
    """Raised when an approved local compatibility smoke cannot proceed."""


def scope_payload(profile_id: str) -> dict[str, Any]:
    try:
        manifest = PROFILE_MANIFESTS[profile_id]
    except KeyError as error:
        raise SmokeError("profile is unsupported") from error
    source_files = {name: _sha256(ROOT / name) for name in SCOPE_FILES}
    return {
        "action": "stage exact allowlisted materials if absent; then perform one synthetic in-process choice; no network during model load or inference",
        "platform": platform.platform(),
        "profile_id": profile_id,
        "profile_manifest": manifest,
        "python": sys.version.split()[0],
        "poetry_lock_sha256": _sha256(ROOT / "poetry.lock"),
        "receipt_path": str(_receipt_path(profile_id).relative_to(ROOT)),
        "scope_files": source_files,
    }


def scope_digest(profile_id: str) -> str:
    return hashlib.sha256(_canonical_json(scope_payload(profile_id))).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_ready(profile_id: str) -> None:
    if _sha256(ROOT / "poetry.lock") != POETRY_LOCK_SHA256:
        raise SmokeError("the optional-runtime Poetry lock changed")
    expected = PROFILE_MANIFESTS[profile_id]["packages"]
    for package, version in expected.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise SmokeError(
                "the selected optional runtime is not installed"
            ) from error
        if actual != version:
            raise SmokeError("the selected optional runtime version does not match")
    if profile_id == "laya-mlx" and (
        platform.system() != "Darwin" or platform.machine() != "arm64"
    ):
        raise SmokeError("Laya-MLX requires Apple Silicon macOS")


def stage_profile(profile_id: str, material_root: Path) -> Path:
    manifest = PROFILE_MANIFESTS[profile_id]
    allow_patterns = [*manifest["files"], *manifest["git_files"]]
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise SmokeError(
            "the selected runtime lacks Hugging Face Hub support"
        ) from error
    return Path(
        snapshot_download(
            repo_id=manifest["model_id"],
            revision=manifest["model_revision"],
            local_dir=material_root / profile_id,
            allow_patterns=allow_patterns,
        )
    )


def verify_materials(profile_id: str, material_dir: Path) -> None:
    profile = preflight.PROFILES[profile_id]
    receipts = [
        preflight._file_receipt(material_dir / name, digest, "sha256")
        for name, digest in profile["files"].items()
    ]
    receipts.extend(
        preflight._file_receipt(material_dir / name, digest, "git-blob-sha1")
        for name, digest in profile.get("git_files", {}).items()
    )
    if any(item["match"] is not True for item in receipts):
        raise SmokeError("exact local material verification failed")


def load_adapter(profile_id: str, material_dir: Path) -> object:
    if profile_id == "von":
        von = importlib.import_module("von")
        backend_module = importlib.import_module("von.backends.option_marker_backend")
        backend = backend_module.OptionMarkerBackend(
            checkpoint_dir=str(material_dir), device="cpu"
        )
        return VonDecisionAdapter(backend, von.Choice)
    if profile_id == "julia1":
        sys.path.insert(0, str(material_dir))
        julia = importlib.import_module("julia")
        engine = julia.load_model(str(material_dir), device="cpu", backend="torch")
        return Julia1DecisionAdapter(engine)
    if profile_id == "laya-mlx":
        laya = importlib.import_module("laya_mlx")
        agent = laya.load(str(material_dir), device="gpu", dtype="float16")
        return LayaMLXDecisionAdapter(agent)
    raise SmokeError("profile is unsupported")


def decision_profile(profile_id: str) -> DecisionModelProfile:
    identity = IDENTITIES[profile_id]
    max_tokens = 1024 if profile_id == "laya-mlx" else 8192
    return DecisionModelProfile(
        identity=identity,
        max_input_bytes=32768,
        max_input_tokens=max_tokens,
        max_questions=1,
        max_options_per_question=3,
        max_result_bytes=8192,
        supported_modes=frozenset({DecisionMode.CHOICE}),
    )


def _receipt_path(profile_id: str) -> Path:
    return (
        ROOT
        / "specs"
        / "decision-model-support"
        / "evaluation"
        / (f"dms16-smoke-{profile_id}.json")
    )


def run_profile(
    profile_id: str,
    material_root: Path,
    approved_scope: str | None,
    *,
    stage: Any | None = None,
    load: Any | None = None,
) -> dict[str, Any]:
    expected_scope = scope_digest(profile_id)
    if approved_scope != expected_scope:
        raise SmokeError(
            f"approval is absent or does not match; required scope: {expected_scope}"
        )
    receipt_path = _receipt_path(profile_id)
    if receipt_path.exists():
        raise SmokeError("a smoke receipt already exists for this one-run approval")
    _runtime_ready(profile_id)
    missing_before_staging = not _materials_present(
        profile_id, material_root / profile_id
    )
    material_dir, adapter = _stage_and_load(profile_id, material_root, stage, load)
    profile = decision_profile(profile_id)
    elapsed_ms = _invoke_smoke(
        profile_id, adapter, profile, expected_scope, receipt_path
    )
    report = {
        "approval_scope": expected_scope,
        "profile_id": profile_id,
        "model_id": PROFILE_MANIFESTS[profile_id]["model_id"],
        "model_revision": PROFILE_MANIFESTS[profile_id]["model_revision"],
        "source_revision": PROFILE_MANIFESTS[profile_id]["source_revision"],
        "runtime_lock_sha256": POETRY_LOCK_SHA256,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "material_file_count": len(preflight.PROFILES[profile_id]["files"])
        + len(preflight.PROFILES[profile_id].get("git_files", {})),
        "missing_materials_before_staging": missing_before_staging,
        "inference_count": 1,
        "result_valid": True,
        "elapsed_ms": elapsed_ms,
        "network_disabled_before_load": True,
    }
    write_receipt(receipt_path, report)
    return report


def _materials_present(profile_id: str, material_dir: Path) -> bool:
    profile = preflight.PROFILES[profile_id]
    filenames = (*profile["files"], *profile.get("git_files", {}))
    return all((material_dir / name).is_file() for name in filenames)


def _stage_and_load(
    profile_id: str, material_root: Path, stage: Any | None, load: Any | None
) -> tuple[Path, object]:
    try:
        material_dir = (stage or stage_profile)(profile_id, material_root)
        verify_materials(profile_id, material_dir)
    except SmokeError:
        raise
    except Exception as error:
        raise SmokeError("local material staging or verification failed") from error
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        adapter = (load or load_adapter)(profile_id, material_dir)
    except Exception as error:
        raise SmokeError("local model loading failed") from error
    return material_dir, adapter


def _invoke_smoke(
    profile_id: str,
    adapter: object,
    profile: DecisionModelProfile,
    expected_scope: str,
    receipt_path: Path,
) -> float:
    request = DecisionModelRequest(
        decision_id=f"dms16-{profile_id}-compatibility-smoke",
        context=_SYNTHETIC_STATE,
        questions=(DecisionQuestion("route", _SYNTHETIC_OPTIONS, _SYNTHETIC_QUESTION),),
        mode=DecisionMode.CHOICE,
    )
    if receipt_path is not None:
        reserve_receipt(
            receipt_path,
            {
                "profile_id": profile_id,
                "approval_scope": expected_scope,
                "status": "inference_started",
            },
        )
    started = time.monotonic()
    try:
        result = adapter.decide(request)
    except Exception as error:
        _write_failure_receipt(
            receipt_path, profile_id, expected_scope, "inference_failed"
        )
        raise SmokeError("the adapter-facing smoke failed") from error
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if not isinstance(result, DecisionModelResult):
        _write_failure_receipt(
            receipt_path, profile_id, expected_scope, "result_invalid"
        )
        raise SmokeError("the adapter-facing smoke returned an invalid result")
    try:
        validate_decision_result(result, request, profile)
    except Exception as error:
        _write_failure_receipt(
            receipt_path, profile_id, expected_scope, "result_invalid"
        )
        raise SmokeError(
            "the adapter-facing smoke returned an invalid result"
        ) from error
    return elapsed_ms


def _write_failure_receipt(
    path: Path, profile_id: str, scope: str, status: str
) -> None:
    write_receipt(
        path,
        {"profile_id": profile_id, "approval_scope": scope, "status": status},
    )


def write_receipt(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def reserve_receipt(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_id", choices=sorted(PROFILE_MANIFESTS))
    parser.add_argument(
        "--material-root", type=Path, default=Path("/private/tmp/dms16-materials")
    )
    parser.add_argument("--print-scope", action="store_true")
    parser.add_argument("--approve-scope")
    args = parser.parse_args()
    expected_scope = scope_digest(args.profile_id)
    if args.print_scope:
        print(
            json.dumps(
                {
                    "profile_id": args.profile_id,
                    "approval_scope": expected_scope,
                    "scope": scope_payload(args.profile_id),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    try:
        report = run_profile(
            args.profile_id,
            args.material_root,
            args.approve_scope,
        )
    except SmokeError as error:
        print(json.dumps({"profile_id": args.profile_id, "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
