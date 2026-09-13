"""Host-owned preparation of reviewed multi-file local-model recipes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Literal

from dynamic_agent_runner.hugging_face_support import (
    HuggingFaceSupportError,
    download_hub_file,
)
from dynamic_agent_runner.local_models import HuggingFaceModelFileReference


PreparationStatus = Literal[
    "ready",
    "recipe_unavailable",
    "preparation_not_authorized",
    "source_unavailable",
    "integrity_failed",
    "conversion_failed",
]
DownloadFile = Callable[[HuggingFaceModelFileReference, Path], Path]
Converter = Callable[
    ["LocalModelPreparationRecipe", Mapping[str, Path], Path],
    None,
]
CommandRunner = Callable[[Sequence[str], Path], None]


class LocalModelPreparationUnavailable(ValueError):
    """Raised when a reviewed recipe or verified prepared set is unavailable."""


@dataclass(frozen=True)
class LocalModelArtifact:
    """One exact source artifact belonging to a reviewed recipe."""

    role: str
    repo_id: str
    revision: str
    filename: str
    sha256: str
    group: str = ""

    def reference(self) -> HuggingFaceModelFileReference:
        """Return the package-owned Hub reference for this pinned source."""

        return HuggingFaceModelFileReference(
            repo_id=self.repo_id, filename=self.filename, revision=self.revision
        )


@dataclass(frozen=True)
class LocalModelTransformation:
    """One reviewed deterministic transform and its verified result."""

    converter_revision: str
    output_role: str
    output_filename: str
    output_sha256: str


@dataclass(frozen=True)
class LocalModelLoaderProfile:
    """One closed runtime loading profile selected by a reviewed recipe."""

    profile_id: str


TRANSFORMERS_PEFT_SINGLE_IMAGE_V1 = LocalModelLoaderProfile(
    "transformers-peft-single-image-v1"
)

QWEN25_VL_3B_FLOORPLAN_GRPO_MODEL_ID = "qwen25-vl-3b-floorplan-grpo"
QWEN25_VL_3B_FLOORPLAN_GRPO_ADAPTER_ID = (
    "qwen25-vl-3b-floorplan-grpo-transformers-peft-adapter-v1"
)


def qwen25_vl_3b_floorplan_grpo_recipe() -> "LocalModelPreparationRecipe":
    """Return the reviewed native Transformers/PEFT floorplan materials."""

    base_revision = "66285546d2b821cf421d4f5eb2576359d3770cd3"
    adapter_revision = "784b8bf4705939887122bcfba029a6fce13e9ff4"
    base = (
        (
            "base_config",
            "config.json",
            "7ed3eed5be6924cc800e8a5e53fc405c1aab1aaf36bad65c33403b36c56827f5",
        ),
        (
            "base_generation_config",
            "generation_config.json",
            "533f191cc257b7de37a4fccd0a7a1706d75e1aa660f93efaa54e5a2a9f9aace9",
        ),
        (
            "base_chat_template",
            "chat_template.json",
            "ad60d90252ed0b0705ba14e2d0ad0fec0beac1ea955642b54059b36052d8bc96",
        ),
        (
            "base_weight_index",
            "model.safetensors.index.json",
            "c7dd78a4c6bea60b51332f1baf37b8f8124ecab2c35395a29a29825bf2619768",
        ),
        (
            "base_weight_1",
            "model-00001-of-00002.safetensors",
            "41a8895c164b4d32bae6b302f4603fcbc1797f32dafa45c7e9bcda23c6755df8",
        ),
        (
            "base_weight_2",
            "model-00002-of-00002.safetensors",
            "365531ff8752420e89dee707b79d021fb2d6e25abafe486f080555a4fe6972e4",
        ),
        (
            "processor_config",
            "preprocessor_config.json",
            "f2058c716eef96ccaed1cc1e2d0c08306b62586d535b28d9d08e691b2fab7ca0",
        ),
        (
            "processor_tokenizer",
            "tokenizer.json",
            "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
        ),
        (
            "processor_tokenizer_config",
            "tokenizer_config.json",
            "4abd3520120e266da84c0864fee064d1fb10806f02225911a47253dd38dc5f56",
        ),
        (
            "processor_vocab",
            "vocab.json",
            "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
        ),
        (
            "processor_merges",
            "merges.txt",
            "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3",
        ),
    )
    artifacts = tuple(
        LocalModelArtifact(
            role, "Qwen/Qwen2.5-VL-3B-Instruct", base_revision, filename, digest, "base"
        )
        for role, filename, digest in base
    ) + (
        LocalModelArtifact(
            "adapter_config",
            "mudasir13cs/qwen25-vl-3b-floorplan-grpo",
            adapter_revision,
            "adapter_config.json",
            "d4378af112087c3421851cb9ebde13fee0abc0ee1f001e0499d8febe62caf729",
            "adapter",
        ),
        LocalModelArtifact(
            "adapter_weights",
            "mudasir13cs/qwen25-vl-3b-floorplan-grpo",
            adapter_revision,
            "adapter_model.safetensors",
            "089892a8815310bce15d6bf6d1fb082926f46a135b9550c6381ac192901d0132",
            "adapter",
        ),
    )
    return LocalModelPreparationRecipe(
        QWEN25_VL_3B_FLOORPLAN_GRPO_MODEL_ID,
        QWEN25_VL_3B_FLOORPLAN_GRPO_ADAPTER_ID,
        artifacts,
        None,
        "transformers-peft-v1",
        loader_profile=TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )


@dataclass(frozen=True)
class LocalModelPreparationRecipe:
    """A host-owned mapping of one logical model to exact runtime artifacts."""

    model_id: str
    adapter_id: str
    artifacts: tuple[LocalModelArtifact, ...]
    transformation: LocalModelTransformation | None
    runner_id: str = "llama-cpp-v1"
    recipe_id: str = ""
    loader_profile: LocalModelLoaderProfile | None = None

    def __post_init__(self) -> None:
        if not self.recipe_id:
            object.__setattr__(
                self,
                "recipe_id",
                f"{self.model_id}:{self.adapter_id}:{self.runner_id}",
            )

    @property
    def recipe_digest(self) -> str:
        """Return the canonical identity for this immutable recipe."""

        payload = {
            "recipe_id": self.recipe_id,
            "model_id": self.model_id,
            "adapter_id": self.adapter_id,
            "runner_id": self.runner_id,
            "loader_profile": (
                None if self.loader_profile is None else self.loader_profile.profile_id
            ),
            "artifacts": [
                {
                    "role": item.role,
                    "repo_id": item.repo_id,
                    "revision": item.revision,
                    "filename": item.filename,
                    "sha256": item.sha256,
                    "group": item.group,
                }
                for item in self.artifacts
            ],
            "transformation": (
                None
                if self.transformation is None
                else {
                    "converter_revision": self.transformation.converter_revision,
                    "output_role": self.transformation.output_role,
                    "output_filename": self.transformation.output_filename,
                    "output_sha256": self.transformation.output_sha256,
                }
            ),
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, repr=False)
class PreparedArtifactSet:
    """Host-private verified paths for one runtime-ready recipe."""

    recipe: LocalModelPreparationRecipe
    paths: Mapping[str, Path]

    @property
    def recipe_id(self) -> str:
        """Return the host-private recipe identity for this set."""

        return self.recipe.recipe_id

    @property
    def recipe_digest(self) -> str:
        """Return the host-private digest for this set."""

        return self.recipe.recipe_digest

    def group_path(self, group: str) -> Path:
        """Return one verified private materialization group root."""

        for artifact in self.recipe.artifacts:
            if (artifact.group or artifact.role) == group:
                return self.paths[artifact.role].parent
        raise KeyError(group)


@dataclass(frozen=True)
class LocalModelPreparationResult:
    """Path-free public outcome of an attempted preparation."""

    model_id: str
    status: PreparationStatus


class LocalModelPreparationCatalog:
    """Exact-match catalog; it deliberately has no discovery or fallback."""

    def __init__(self, recipes: Sequence[LocalModelPreparationRecipe]) -> None:
        prepared: dict[tuple[str, str, str], LocalModelPreparationRecipe] = {}
        for item in recipes:
            if not all(
                isinstance(value, str) and value
                for value in (
                    item.model_id,
                    item.adapter_id,
                    item.runner_id,
                    item.recipe_id,
                )
            ):
                raise LocalModelPreparationUnavailable("recipe_invalid")
            key = (item.model_id, item.adapter_id, item.runner_id)
            if key in prepared:
                raise LocalModelPreparationUnavailable("recipe_invalid")
            if not _valid_loader_profile(item):
                raise LocalModelPreparationUnavailable("recipe_invalid")
            prepared[key] = item
        self._recipes = prepared

    def lookup(
        self, model_id: str, adapter_id: str, runner_id: str = "llama-cpp-v1"
    ) -> LocalModelPreparationRecipe:
        """Return one reviewed recipe or a stable unavailable error."""

        try:
            return self._recipes[(model_id, adapter_id, runner_id)]
        except KeyError as error:
            raise LocalModelPreparationUnavailable("recipe_unavailable") from error


_TRANSFORMERS_PEFT_BASE_ROLES = frozenset(
    {
        "base_config",
        "base_generation_config",
        "base_chat_template",
        "base_weight_index",
        "base_weight_1",
        "base_weight_2",
        "processor_config",
        "processor_tokenizer",
        "processor_tokenizer_config",
        "processor_vocab",
        "processor_merges",
    }
)
_TRANSFORMERS_PEFT_ADAPTER_ROLES = frozenset({"adapter_config", "adapter_weights"})


def _valid_loader_profile(recipe: LocalModelPreparationRecipe) -> bool:
    """Return whether a recipe satisfies its one declared loading profile."""

    if recipe.runner_id != "transformers-peft-v1":
        return recipe.loader_profile is None
    if recipe.loader_profile != TRANSFORMERS_PEFT_SINGLE_IMAGE_V1:
        return False
    if recipe.transformation is not None:
        return False
    base_roles = frozenset(
        item.role for item in recipe.artifacts if item.group == "base"
    )
    adapter_roles = frozenset(
        item.role for item in recipe.artifacts if item.group == "adapter"
    )
    return (
        base_roles == _TRANSFORMERS_PEFT_BASE_ROLES
        and adapter_roles == _TRANSFORMERS_PEFT_ADAPTER_ROLES
        and len(base_roles) + len(adapter_roles) == len(recipe.artifacts)
    )


class PinnedLlamaCppLoraConverter:
    """Run one host-provisioned llama.cpp converter at its reviewed revision."""

    def __init__(
        self,
        *,
        checkout: Path,
        launcher: Path | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._checkout = checkout
        self._launcher = launcher or Path(__file__).parents[2] / "tools" / (
            "llama_cpp_lora_converter.py"
        )
        self._command_runner = command_runner or _run_converter_command

    def __call__(
        self,
        recipe: LocalModelPreparationRecipe,
        sources: Mapping[str, Path],
        output: Path,
    ) -> None:
        """Convert only the fixed recipe's declared LoRA and metadata inputs."""

        if recipe.transformation.converter_revision != self._ensure_checkout(
            recipe.transformation.converter_revision
        ):
            raise RuntimeError("reviewed converter is unavailable")
        if not self._launcher.is_file():
            raise RuntimeError("reviewed converter is unavailable")
        try:
            lora = sources["source_lora"]
            lora_metadata = sources["lora_metadata"]
            base_metadata = sources["base_configuration_metadata"]
        except KeyError as error:
            raise RuntimeError("reviewed converter inputs are unavailable") from error
        self._command_runner(
            (
                "uv",
                "run",
                "--script",
                str(self._launcher),
                "--converter-root",
                str(self._checkout),
                "--lora-model",
                str(lora),
                "--lora-config",
                str(lora_metadata),
                "--base-config",
                str(base_metadata),
                "--output",
                str(output),
            ),
            self._checkout,
        )

    def _ensure_checkout(self, revision: str) -> str:
        if self._checkout.exists():
            return _checkout_revision(self._checkout)
        self._checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            (
                "git",
                "init",
                str(self._checkout),
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self._checkout),
                "remote",
                "add",
                "origin",
                "https://github.com/ggml-org/llama.cpp.git",
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self._checkout),
                "fetch",
                "--depth",
                "1",
                "origin",
                revision,
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self._checkout),
                "checkout",
                "--detach",
                "FETCH_HEAD",
            ),
            check=True,
            capture_output=True,
        )
        return _checkout_revision(self._checkout)


class LocalModelPreparationService:
    """Prepare only catalogued files in a DAR-owned private cache."""

    def __init__(
        self,
        *,
        catalog: LocalModelPreparationCatalog,
        cache_root: Path,
        approved_cache_roots: Sequence[Path] = (),
        download_file: DownloadFile | None = None,
        converter: Converter | None = None,
    ) -> None:
        self._catalog = catalog
        self._cache_root = cache_root
        self._approved_cache_roots = tuple(approved_cache_roots)
        self._download_file = download_file or _download_file
        self._converter = converter or _unavailable_converter

    def prepare(
        self,
        *,
        model_id: str,
        adapter_id: str,
        authorized: bool,
        runner_id: str = "llama-cpp-v1",
    ) -> LocalModelPreparationResult:
        """Prepare one reviewed logical requirement without exposing paths."""

        try:
            recipe = self._catalog.lookup(model_id, adapter_id, runner_id)
        except LocalModelPreparationUnavailable:
            return LocalModelPreparationResult(model_id, "recipe_unavailable")
        if self._ready(recipe) is not None:
            return LocalModelPreparationResult(model_id, "ready")
        if not authorized:
            return LocalModelPreparationResult(model_id, "preparation_not_authorized")
        try:
            sources = self._ensure_sources(recipe)
            self._convert(recipe, sources)
        except _IntegrityError:
            return LocalModelPreparationResult(model_id, "integrity_failed")
        except _ConversionError:
            return LocalModelPreparationResult(model_id, "conversion_failed")
        except (HuggingFaceSupportError, OSError, ValueError):
            return LocalModelPreparationResult(model_id, "source_unavailable")
        return LocalModelPreparationResult(
            model_id, "ready" if self._ready(recipe) is not None else "integrity_failed"
        )

    def resolve(
        self, *, model_id: str, adapter_id: str, runner_id: str = "llama-cpp-v1"
    ) -> PreparedArtifactSet:
        """Return host-private paths only when the entire set remains verified."""

        recipe = self._catalog.lookup(model_id, adapter_id, runner_id)
        prepared = self._ready(recipe)
        if prepared is None:
            raise LocalModelPreparationUnavailable("preparation_required")
        return prepared

    def recipe_digest(
        self, *, model_id: str, adapter_id: str, runner_id: str = "llama-cpp-v1"
    ) -> str:
        """Return the exact reviewed recipe identity without exposing paths."""

        return self._catalog.lookup(model_id, adapter_id, runner_id).recipe_digest

    def source_path(
        self, recipe: LocalModelPreparationRecipe, artifact: LocalModelArtifact
    ) -> Path:
        """Return the DAR-owned source-cache path for one declared artifact."""

        group = artifact.group or artifact.role
        return self._recipe_root(recipe) / "sources" / group / artifact.filename

    def output_path(self, recipe: LocalModelPreparationRecipe) -> Path:
        """Return the DAR-owned transformed-output path for one recipe."""

        if recipe.transformation is None:
            raise LocalModelPreparationUnavailable("recipe_invalid")
        return (
            self._recipe_root(recipe)
            / "outputs"
            / recipe.transformation.output_filename
        )

    def _recipe_root(self, recipe: LocalModelPreparationRecipe) -> Path:
        return self._cache_root / recipe.recipe_digest

    def _ready(self, recipe: LocalModelPreparationRecipe) -> PreparedArtifactSet | None:
        paths: dict[str, Path] = {}
        for artifact in recipe.artifacts:
            path = self._verified_source(
                recipe,
                artifact,
                allow_approved_cache=recipe.runner_id != "transformers-peft-v1",
            )
            if path is None:
                return None
            paths[artifact.role] = path
        if recipe.transformation is not None:
            output = self.output_path(recipe)
            if not _matches_sha256(output, recipe.transformation.output_sha256):
                return None
            if not _is_gguf(output):
                return None
            paths[recipe.transformation.output_role] = output
        return PreparedArtifactSet(recipe=recipe, paths=paths)

    def _verified_source(
        self,
        recipe: LocalModelPreparationRecipe,
        artifact: LocalModelArtifact,
        *,
        allow_approved_cache: bool = True,
    ) -> Path | None:
        own = self.source_path(recipe, artifact)
        if _matches_sha256(own, artifact.sha256):
            return own
        if not allow_approved_cache:
            return None
        for root in self._approved_cache_roots:
            candidate = _hub_cache_path(root, artifact)
            if _matches_sha256(candidate, artifact.sha256):
                return candidate
        return None

    def _ensure_sources(
        self, recipe: LocalModelPreparationRecipe
    ) -> Mapping[str, Path]:
        sources: dict[str, Path] = {}
        for artifact in recipe.artifacts:
            source = self._verified_source(recipe, artifact)
            target = self.source_path(recipe, artifact)
            if source is None:
                downloaded = self._download_file(artifact.reference(), self._cache_root)
                if not _matches_sha256(downloaded, artifact.sha256):
                    raise _IntegrityError
                source = downloaded
            if source != target:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                source = target
            if not _matches_sha256(source, artifact.sha256):
                raise _IntegrityError
            sources[artifact.role] = source
        return sources

    def _convert(
        self, recipe: LocalModelPreparationRecipe, sources: Mapping[str, Path]
    ) -> None:
        if recipe.transformation is None:
            return
        output = self.output_path(recipe)
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = output.with_suffix(output.suffix + ".staging")
        try:
            if staging.exists():
                staging.unlink()
            self._converter(recipe, sources, staging)
            if not _is_gguf(staging) or not _matches_sha256(
                staging, recipe.transformation.output_sha256
            ):
                raise _IntegrityError
            staging.replace(output)
        except _IntegrityError:
            staging.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise
        except Exception as error:  # noqa: BLE001 - converter is injected.
            staging.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise _ConversionError from error


class _IntegrityError(Exception):
    pass


class _ConversionError(Exception):
    pass


def _matches_sha256(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def _is_gguf(path: Path) -> bool:
    try:
        return path.read_bytes()[:4] == b"GGUF"
    except OSError:
        return False


def _hub_cache_path(root: Path, artifact: LocalModelArtifact) -> Path:
    return (
        root
        / f"models--{artifact.repo_id.replace('/', '--')}"
        / "snapshots"
        / artifact.revision
        / artifact.filename
    )


def _download_file(reference: HuggingFaceModelFileReference, cache_root: Path) -> Path:
    return download_hub_file(
        repo_id=reference.repo_id,
        filename=reference.filename,
        revision=reference.revision,
        cache_dir=cache_root,
    )


def _checkout_revision(checkout: Path) -> str:
    result = subprocess.run(
        ("git", "-C", str(checkout), "rev-parse", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_converter_command(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)


def _unavailable_converter(
    _recipe: LocalModelPreparationRecipe, _sources: Mapping[str, Path], _output: Path
) -> None:
    raise RuntimeError("reviewed converter is unavailable")
