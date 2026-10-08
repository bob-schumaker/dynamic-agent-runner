#!/usr/bin/env python3
"""Check DMS-16 local artifacts and installed extras without loading models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POETRY_LOCK_SHA256 = "6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a"
PROFILES: dict[str, dict[str, Any]] = {
    "von": {
        "model_id": "wfzyx/von",
        "model_revision": "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae",
        "source_revision": "fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54",
        "runtime_lock_sha256": "acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41",
        "runtime_lock_path": "/private/tmp/dms16-poetry-von/dynamic-agent-runner-liR8DTmq-py3.14/src/von/uv.lock",
        "files": {
            "model.safetensors": "af57d5d2ab15715a753a1eb4add4271d1aecce7e76f3365f629c082df329297a",
            "option_marker.pt": "3faf27f88d30aaf9aa37860d4cdef99f1d05450cf40364f6236ac892d4d139ed",
            "marker_calibration.json": "9b32949dcd0cfd122db509c9bd5be67f0cfe35696153aa93d667caf0aae147c9",
        },
        "git_files": {
            "config.json": "2bf6db3d7991d07aee0fa2743959a3c8f4ff5e4e",
            "tokenizer.json": "31e99eddb04ca32c7c1f66cde30dc3e54099402f",
            "tokenizer_config.json": "185556e53fe0b9c6f0decd322897041e91d8ace4",
        },
        "python": "/private/tmp/dms16-von-compatible-py314/bin/python",
        "python_313": "/private/tmp/dms16-von-compatible-py313/bin/python",
        "packages": {
            "accelerate": "1.15.0",
            "huggingface-hub": "1.32.0",
            "torch": "2.14.0",
            "transformers": "5.17.0",
            "von-sdk": "1.2.3",
        },
    },
    "julia1": {
        "model_id": "SupersonicLabs/Julia-1",
        "model_revision": "a85b127321d580d65176c89ced8273f305745d85",
        "source_revision": "a85b127321d580d65176c89ced8273f305745d85",
        "files": {
            "model.safetensors": "df853bf7fe424420011f3d0c47a05d7341aa9eefa7fb9f203ea4aada4ad95b72",
            "encoder/config.json": "c79cda42d42ddf777218254845ce92fb25a10dc35874be40d06abd707894523d",
            "julia_config.json": "b9b881646beeac5414eaa78b39d3fe89ff8a2c062731ad718432620f9aee6bf7",
            "tokenizer/tokenizer.json": "609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f",
            "tokenizer/tokenizer_config.json": "6b069e57db0ce0794c22547725275f22618809c4ef4249307337e651a0dfef8c",
            "julia/__init__.py": "02485eb4dd7dadd13907380d1a9c3398709bd8af54b3e0e12b3061a3ebb5c1da",
            "julia/cuda.py": "138ab63182f25473ce3886296c47ac44e94fc50ae5270927ae4c373f7bb49137",
            "julia/data.py": "e3510fa4152ec11fa193046715991f44d7c2f85fd2488a98ef11c9d3db23da4e",
            "julia/inference.py": "79b4e716365a6e07da4580ead725d5b76d06ef3a824a3ec23738feba64704b36",
            "julia/model.py": "ef2ba82fe20cdf0db7bb887e9ef075476ed08b985ce9a95be0de3e26246ecc81",
            "julia/probabilities.py": "2a0197d2e0fa5a3c4b06b93599a85706724df7b0d2cc821a13ed293aef59f206",
            "julia/typed.py": "ed89e66a70fcedac1339347bd8fcca69fd2cd1a31535ad0148dae42c610b544d",
            "julia/router/__init__.py": "832cf0a44569941efba66dfa7099b645fdb1084082e40c6115bb0ac5edd78a96",
            "julia/router/encoder.py": "df25efee2ed916d52af9c4e9c0d98e80854ca70bbfc8140f1de871f290fd3238",
            "julia/router/engine.py": "91bb30987ff8626ed1610955c6fd796939a5d271e2405b73f8674ccb947eb931",
            "julia/router/native.py": "42bdba5ea7d874e1f53b2f17e99e731789611b5bd6734f687eaa2b0262c5d7ae",
            "julia/router/router.py": "624b0b82fd34e4c6874a37595fa91a1d79553d0ca9d8111ef8330ed805f6be7c",
        },
        "python": "/private/tmp/dms16-poetry-envs/dynamic-agent-runner-liR8DTmq-py3.14/bin/python",
        "python_313": "/private/tmp/dms16-poetry-py313/dynamic-agent-runner-liR8DTmq-py3.13/bin/python",
        "packages": {
            "torch": "2.14.0",
            "transformers": "5.0.0",
            "tokenizers": "0.22.2",
            "safetensors": "0.8.0",
            "numpy": "2.5.3",
        },
    },
    "laya-mlx": {
        "model_id": "aac6fef/laya-typed-decisions-mlx",
        "model_revision": "28416e78cb26a239a4eabaa2e084904ec5e6cacb",
        "source_revision": "0a859518634112655cb97c745dbf04f5191aaf13",
        "files": {
            "model.safetensors": "804ef8802b4cac7a67913b0cfb8448659e934a50284aaa867b98d7d9a6e7d1e0",
        },
        "git_files": {
            "encoder/config.json": "d4be4829750fb04c0aa8b9897c3ea827f76c0109",
            "mlx_config.json": "47516cb633704ddc43a121566e00b925133c2669",
            "rl_agent_config.json": "d0293fddc8b337c9bc651f2a7b95c0848fbbb488",
            "tokenizer/tokenizer.json": "2f4d8583e507b7466d2490e2d6c045647a822698",
            "tokenizer/tokenizer_config.json": "ed1ffabc2ce11120754705709569e365e46da71a",
        },
        "python": "/private/tmp/dms16-poetry-laya/dynamic-agent-runner-liR8DTmq-py3.14/bin/python",
        "python_313": "/private/tmp/dms16-laya-py313/dynamic-agent-runner-liR8DTmq-py3.13/bin/python",
        "packages": {
            "laya-mlx": "0.2.0",
            "mlx": "0.32.2",
            "numpy": "2.5.3",
            "huggingface-hub": "1.33.0",
        },
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _file_receipt(path: Path, expected: str, algorithm: str) -> dict[str, Any]:
    actual = (
        (
            _sha256(path)
            if algorithm == "sha256"
            else _git_blob_sha1(path)
            if algorithm == "git-blob-sha1"
            else None
        )
        if path.is_file()
        else None
    )
    return {
        "path": str(path),
        "algorithm": algorithm,
        "expected": expected,
        "actual": actual,
        "match": actual == expected,
    }


def _runtime_versions(executable: Path, expected: dict[str, str]) -> dict[str, str]:
    script = (
        "import importlib.metadata as m,json,sys; "
        "names=json.loads(sys.argv[1]); "
        "print(json.dumps({n:m.version(n) for n in names}))"
    )
    result = subprocess.run(
        [str(executable), "-c", script, json.dumps(list(expected))],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if result.returncode:
        return {}
    try:
        versions = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return versions if isinstance(versions, dict) else {}


def build_preflight(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = ROOT / "poetry.lock"
    lock_sha256 = _sha256(lock_path)
    memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    storage_path = (
        args.material_root if args.material_root.is_dir() else args.material_root.parent
    )
    disk = shutil.disk_usage(storage_path)
    rows: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    julia_source_files = {
        path: digest
        for path, digest in PROFILES["julia1"]["files"].items()
        if path.startswith("julia/") and path.endswith(".py")
    }
    julia_source_review = []
    for relative, expected_sha256 in julia_source_files.items():
        path = args.julia_source_root / relative
        actual_sha256 = _sha256(path) if path.is_file() else None
        julia_source_review.append(
            {
                "path": str(path),
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "match": actual_sha256 == expected_sha256,
            }
        )

    for name, profile in PROFILES.items():
        profile_lock_path = Path(profile.get("runtime_lock_path", lock_path))
        expected_profile_lock = profile.get("runtime_lock_sha256", POETRY_LOCK_SHA256)
        profile_lock_sha256 = (
            _sha256(profile_lock_path) if profile_lock_path.is_file() else None
        )
        model_dir = args.material_root / name
        files = [
            _file_receipt(model_dir / filename, expected, "sha256")
            for filename, expected in profile["files"].items()
        ]
        files.extend(
            _file_receipt(model_dir / filename, expected, "git-blob-sha1")
            for filename, expected in profile.get("git_files", {}).items()
        )
        executable = Path(profile["python"])
        executable_313 = Path(profile["python_313"])
        actual_packages = (
            _runtime_versions(executable, profile["packages"])
            if executable.is_file()
            else {}
        )
        actual_packages_313 = (
            _runtime_versions(executable_313, profile["packages"])
            if executable_313.is_file()
            else {}
        )
        packages_match = actual_packages == profile["packages"]
        packages_313_match = actual_packages_313 == profile["packages"]
        row_blockers = [
            f"missing_or_mismatched:{item['path']}"
            for item in files
            if item["match"] is not True
        ]
        if not executable.is_file():
            row_blockers.append("optional_runtime_not_installed")
        elif not packages_match:
            row_blockers.append("optional_runtime_package_versions_mismatch")
        if not executable_313.is_file():
            row_blockers.append("python_3_13_optional_runtime_not_installed")
        elif not packages_313_match:
            row_blockers.append(
                "python_3_13_optional_runtime_package_versions_mismatch"
            )
        if profile_lock_sha256 != expected_profile_lock:
            row_blockers.append("profile_runtime_lock_mismatch")
        rows[name] = {
            "model_id": profile["model_id"],
            "model_revision": profile["model_revision"],
            "source_revision": profile["source_revision"],
            "files": files,
            "runtime_executable": str(executable),
            "runtime_packages": actual_packages,
            "python_3_13_runtime_executable": str(executable_313),
            "python_3_13_runtime_packages": actual_packages_313,
            "python_3_13_runtime_matches": packages_313_match,
            "profile_runtime_lock_path": str(profile_lock_path),
            "runtime_lock_sha256": profile_lock_sha256,
            "expected_runtime_lock_sha256": expected_profile_lock,
            "runtime_lock_matches": profile_lock_sha256 == expected_profile_lock,
            "blockers": row_blockers,
        }
        blockers.extend(f"{name}:{item}" for item in row_blockers)

    if lock_sha256 != POETRY_LOCK_SHA256:
        blockers.append("root_poetry_lock_changed_since_optional_install_checks")
    return {
        "host": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "total_memory_bytes": memory_bytes,
            "material_root": str(args.material_root),
            "storage_checked_at": str(storage_path),
            "free_storage_bytes": disk.free,
        },
        "julia_source_review": {
            "source_revision": PROFILES["julia1"]["source_revision"],
            "source_root": str(args.julia_source_root),
            "files": julia_source_review,
            "all_hashes_match": all(item["match"] for item in julia_source_review),
            "model_runtime_invoked": False,
        },
        "root_poetry_lock_sha256": lock_sha256,
        "profiles": rows,
        "technical_preflight_pass": not blockers,
        "approval_required_before_download_or_inference": True,
        "inference_performed": False,
        "download_performed": False,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--material-root",
        type=Path,
        default=Path("/private/tmp/dms16-materials"),
        help="Expected local material directory; the script never creates or downloads files.",
    )
    parser.add_argument(
        "--julia-source-root",
        type=Path,
        default=Path("/private/tmp/dms16-julia-source"),
        help="Source-only checkout used for static review; no model loading occurs.",
    )
    args = parser.parse_args()
    receipt = build_preflight(args)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["technical_preflight_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
