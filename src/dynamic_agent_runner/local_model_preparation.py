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
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.model_materials import ModelDependencyLock


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
TRANSFORMERS_PEFT_ADAPTER_ID = "transformers-peft-adapter-v1"
TRANSFORMERS_PEFT_RUNNER_ID = "transformers-peft-v1"


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


def prepared_transformers_peft_recipe(
    *, lock: ModelDependencyLock, binding: ModelExecutionBinding
) -> LocalModelPreparationRecipe:
    """Derive the one closed PEFT loader recipe from sealed execution facts."""

    if (
        binding.logical_model_id != lock.logical_model_id
        or binding.material_lock_digest != lock.digest
        or binding.runner_contract_id != "transformers-generate-v1"
        or binding.runner_contract_version != "1"
        or binding.execution_abi_id != "transformers-peft-generation-v1"
        or binding.execution_abi_version != "1"
        or lock.preparation
    ):
        raise LocalModelPreparationUnavailable("recipe_invalid")
    recipe = LocalModelPreparationRecipe(
        model_id=lock.logical_model_id,
        adapter_id=TRANSFORMERS_PEFT_ADAPTER_ID,
        artifacts=tuple(
            LocalModelArtifact(
                role=source.role,
                repo_id=source.repository,
                revision=source.revision,
                filename=source.filename,
                sha256=source.sha256,
                group=source.group,
            )
            for source in lock.sources
        ),
        transformation=None,
        runner_id=TRANSFORMERS_PEFT_RUNNER_ID,
        recipe_id=f"prepared-transformers-peft:{lock.digest}",
        loader_profile=TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )
    if not _valid_loader_profile(recipe):
        raise LocalModelPreparationUnavailable("recipe_invalid")
    return recipe


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
