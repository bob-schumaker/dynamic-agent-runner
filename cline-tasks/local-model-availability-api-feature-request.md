# Feature Request: Local Model Availability and Cache Discovery API

## Summary

Power Marimo needs a first-class `dynamic-agent-runner` API for discovering and
checking local model availability before a workflow creates an adapter or starts
model execution.

Today the runner can resolve a specific requested local model asset through
`resolve_local_model_path(...)`, but that is a low-level, non-exported path
resolution helper. It answers "can this exact config resolve?" and may download
when network is allowed. It does not provide a public product-facing interface
for questions like:

- Which local models or model files are already available?
- Is this Hugging Face repo/file already cached locally?
- Will selecting this model require a multi-GB download?
- Which cache root or local path will be used?
- Is a cached asset usable for llama.cpp, MLX GGUF, or converted MLX?

Power Marimo can work around this by probing filesystem locations or attempting
adapter creation, but that duplicates runner cache policy and makes the UI
less deliberate.

## Downstream Context

Power Marimo is adding project-local model selection for OpenAI, llama.cpp, and
MLX-backed local models. The project options dialog lets a user choose a model
from Hugging Face and stores the resulting `LlmOptions` in the `.pmproj` file.
The runtime then calls Power Marimo's model selection layer, which delegates to
`dynamic-agent-runner` local model factories.

Recent downstream work added support for selecting this model in the MLX
context:

```text
repo:     empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF
artifact: Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf
```

That model is a GGUF repo, not a converted MLX repo. Power Marimo therefore
relaxed MLX-context Hugging Face search so it can find GGUF repositories, and it
now preserves the selected GGUF artifact when saving MLX project options.

The opt-in live test path now validates:

1. search Hugging Face for `Qwythos-9B-Claude-Mythos-5-1M` through the runner
   backed catalog wrapper
2. select `empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF`
3. preserve artifact `Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf` in the dialog
   produced `LlmOptions`
4. call `select_runner_model(...)`, which delegates to the runner's MLX local
   adapter factory
5. create a small request to force the adapter to resolve/download/load the
   model through runner APIs

This proves the current path works as a runtime setup path, but it is too late
for good UX: the first concrete indication of local availability happens during
model setup/execution, not while the user is choosing the model.

## Current Runner Behavior

The relevant runner implementation is in `dynamic_agent_runner.local_models`.
The helper below does most of what runtime setup needs for one specific asset:

```python
resolve_local_model_path(
    config: LocalModelPathConfig,
    *,
    allow_network: bool = True,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> Path
```

It checks, in order:

1. explicit local path
2. explicit cache root plus `model_filename`
3. default cache root plus `model_filename`
4. Hugging Face file reference, downloading if allowed
5. Hugging Face snapshot reference, downloading if allowed

The default cache root is currently:

```python
Path.home() / ".ollama" / "models"
```

MLX setup calls that resolver from `MLXLocalModelAdapter._resolve_model_path()`
and then validates the resolved path as either GGUF or converted MLX.

That is a useful internal primitive, but it has product-facing limitations:

- It is not exported from the public `dynamic_agent_runner` package surface.
- It resolves one requested asset rather than listing local availability.
- With `allow_network=True`, it may mutate state by downloading.
- With `allow_network=False`, callers can infer absence only by catching an
  exception, not by receiving a structured availability result.
- It does not expose enough metadata for a UI to say where the asset is cached,
  why it is missing, or whether a download would be required.

## Requested API

Please add a public local model availability/discovery API to
`dynamic-agent-runner`.

A concrete shape could be something like this, though the exact names are up to
upstream:

```python
@dataclass(frozen=True)
class LocalModelAssetReference:
    provider: Literal["hugging_face", "local_path"]
    repo_id: str | None = None
    filename: str | None = None
    revision: str | None = None
    explicit_path: Path | None = None
    model_format: Literal["gguf", "mlx", "auto"] = "auto"
    backend: Literal["llama_cpp", "mlx", "auto"] = "auto"

@dataclass(frozen=True)
class LocalModelAvailability:
    status: Literal[
        "available",
        "missing",
        "would_download",
        "invalid",
        "unknown",
    ]
    reference: LocalModelAssetReference
    resolved_path: Path | None = None
    cache_root: Path | None = None
    source: Literal[
        "explicit_path",
        "explicit_cache_root",
        "default_cache_root",
        "hugging_face_cache",
        "not_found",
    ] | None = None
    size_bytes: int | None = None
    message: str = ""
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class LocalModelInventory:
    cache_roots: tuple[Path, ...]
    assets: tuple[LocalModelAvailability, ...]
    warnings: tuple[str, ...] = ()
```

Potential functions:

```python
check_local_model_availability(
    reference: LocalModelAssetReference,
    *,
    cache_roots: Sequence[Path] = (),
    allow_network_metadata: bool = False,
) -> LocalModelAvailability

list_local_model_assets(
    *,
    cache_roots: Sequence[Path] = (),
    include_hugging_face_cache: bool = True,
    include_ollama_cache: bool = True,
    model_formats: Sequence[str] = ("gguf", "mlx"),
) -> LocalModelInventory
```

Important semantic point: `check_local_model_availability(...)` should not
perform a model download. If it needs network metadata to identify size or
remote existence, that should be controlled explicitly with a flag and should
still not download the asset.

## Product Use Cases

### 1. Project options dialog status

Power Marimo wants to show status while the user is selecting a Hugging Face
model:

- "Available locally"
- "Not downloaded; first run will download ~8.3 GiB"
- "Cached file exists but is not a valid GGUF"
- "Converted MLX snapshot is missing tokenizer/weights"
- "Using explicit path `/.../model.gguf`"

That status should be based on the same cache policy the runner will use later.

### 2. Avoid surprise downloads

The user should know before clicking through project options that a model choice
will trigger a large download. Power Marimo can then choose whether to:

- ask for confirmation
- expose a download/preflight action
- show progress separately from the first chat request
- support an offline-only mode cleanly

### 3. Better live test and smoke-test setup

Power Marimo has opt-in live tests for Hugging Face discovery and MLX GGUF
setup. A structured availability API would let those tests assert preconditions
without relying on exception text or accidentally starting a download.

### 4. Consistent behavior across local backends

The same availability shape should work for:

- llama.cpp GGUF file refs
- MLX GGUF file refs
- converted MLX snapshots/directories
- explicit local model paths
- configured cache roots
- runner default cache roots

## Desired Behavior Details

- Do not download during availability checks.
- Return structured statuses instead of requiring callers to interpret
  `LocalModelResolutionError` text.
- Export the API from the public `dynamic_agent_runner` package surface.
- Reuse existing runner cache-root policy rather than making downstream apps
  know where runner-managed assets live.
- Include the effective cache root and resolved path when available.
- Distinguish "remote exists but local asset missing" from "remote or local
  reference is invalid" when network metadata is explicitly allowed.
- Support both file refs and snapshot refs.
- Keep validation backend-aware enough to distinguish GGUF file checks from
  converted MLX directory checks.

## Why This Belongs Upstream

Power Marimo can technically inspect `~/.ollama/models`, Hugging Face cache
folders, and selected filenames itself. That would be the wrong ownership
boundary.

The runner already owns:

- local adapter config types
- cache-root precedence
- Hugging Face file/snapshot download helpers
- GGUF and converted MLX validation rules
- model identity validation
- local-model setup errors

If Power Marimo duplicates local availability logic, it will drift from the
runner's real resolution behavior. The UI might say a model is present while the
runner later downloads, or say a model is missing while the runner would have
found it through a different cache root.

The upstream API should make local model availability inspectable without
forcing downstream products to instantiate adapters or start model execution.

## Downstream Stopgap

For now, Power Marimo can only do three weaker things:

1. use Hugging Face search/verification to prove the remote repo exists
2. save the model repo and artifact into project-local options
3. call `select_runner_model(...)` and let adapter setup resolve/download/load
   the asset on first use

That is acceptable for opt-in live tests, but it is not good enough for a
polished local-model options UI.

## Acceptance Criteria

A good upstream implementation would let Power Marimo write tests like:

```python
availability = dynamic_agent_runner.check_local_model_availability(
    LocalModelAssetReference(
        provider="hugging_face",
        repo_id="empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF",
        filename="Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf",
        model_format="gguf",
        backend="mlx",
    ),
    allow_network_metadata=True,
)

assert availability.status in {"available", "would_download"}
assert availability.reference.repo_id == (
    "empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF"
)
assert availability.reference.filename == (
    "Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf"
)
```

And for local inventory:

```python
inventory = dynamic_agent_runner.list_local_model_assets()
assert any(asset.status == "available" for asset in inventory.assets)
```

Power Marimo would then use those results directly in the project options dialog
and preflight surfaces.
