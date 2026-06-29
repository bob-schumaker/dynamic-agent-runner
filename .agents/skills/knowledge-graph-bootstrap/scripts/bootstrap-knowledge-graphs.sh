#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCOPE=auto
CONFIGURE=1
INDEX=1
DRY_RUN=0
CLEANUP_ONLY=0

usage() {
    cat <<'EOF'
Usage: .agents/skills/knowledge-graph-bootstrap/scripts/bootstrap-knowledge-graphs.sh [options]

Options:
  --scope auto|global|repo  Global-first with fallback, global-only, or repo-only
  --skip-agent-config      Install CLIs but do not configure Codex integrations
  --skip-index             Install/configure only; do not create or refresh indexes
  --cleanup-only           Remove verified legacy Graphify code collateral, then exit
  --dry-run                Print actions without changing anything
  -h, --help               Show this help
EOF
}

while (($#)); do
    case "$1" in
        --scope) SCOPE="${2:-}"; shift 2 ;;
        --skip-agent-config) CONFIGURE=0; shift ;;
        --skip-index) INDEX=0; shift ;;
        --cleanup-only) CLEANUP_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$SCOPE" in auto|global|repo) ;; *) echo "Invalid scope: $SCOPE" >&2; exit 2 ;; esac
cd "$ROOT"

print_cmd() { printf '  '; printf '%q ' "$@"; printf '\n'; }
run() {
    print_cmd "$@"
    ((DRY_RUN)) || "$@"
}
warn() { printf 'warning: %s\n' "$*" >&2; }

global_tool() {
    local name=$1
    command -v "$name" 2>/dev/null || {
        [[ -x "$HOME/.local/bin/$name" ]] && printf '%s\n' "$HOME/.local/bin/$name"
    }
}

tool_path() {
    local name=$1
    global_tool "$name" || {
        [[ -x "$ROOT/.agent-tools/bin/$name" ]] && printf '%s\n' "$ROOT/.agent-tools/bin/$name"
    }
}

selected_tool() {
    local name=$1
    case "$SCOPE" in
        repo) [[ -x "$ROOT/.agent-tools/bin/$name" ]] && printf '%s\n' "$ROOT/.agent-tools/bin/$name" ;;
        global) global_tool "$name" ;;
        auto) tool_path "$name" ;;
    esac
}

tool_ready() {
    local path
    path="$(selected_tool "$1")" || return 1
    "$path" --version >/dev/null 2>&1
}

install_codegraph() {
    local installer="https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh"
    if tool_ready codegraph; then return; fi
    if [[ "$SCOPE" != repo ]]; then
        if ((DRY_RUN)); then
            echo "CodeGraph: install self-contained bundle globally"
            print_cmd curl -fsSL "$installer" -o '<temporary-file>'
            print_cmd sh '<temporary-file>'
            CODEGRAPH="$HOME/.local/bin/codegraph"
            return
        fi
        local tmp
        tmp="$(mktemp)"
        if curl -fsSL "$installer" -o "$tmp" && sh "$tmp"; then
            CODEGRAPH="$HOME/.local/bin/codegraph"
            rm -f "$tmp"; return
        fi
        rm -f "$tmp"
        [[ "$SCOPE" == auto ]] || return 1
        warn "global CodeGraph install failed; falling back to the repository"
    fi
    echo "CodeGraph: install self-contained bundle in .agent-tools"
    if ((DRY_RUN)); then
        print_cmd curl -fsSL "$installer" -o '<temporary-file>'
        print_cmd env CODEGRAPH_INSTALL_DIR="$ROOT/.agent-tools/codegraph" CODEGRAPH_BIN_DIR="$ROOT/.agent-tools/bin" sh '<downloaded-installer>'
        CODEGRAPH="$ROOT/.agent-tools/bin/codegraph"
        return
    fi
    mkdir -p .agent-tools/bin
    local tmp
    tmp="$(mktemp)"
    curl -fsSL "$installer" -o "$tmp"
    CODEGRAPH_INSTALL_DIR="$ROOT/.agent-tools/codegraph" CODEGRAPH_BIN_DIR="$ROOT/.agent-tools/bin" sh "$tmp"
    CODEGRAPH="$ROOT/.agent-tools/bin/codegraph"
    rm -f "$tmp"
}

install_gitnexus() {
    if tool_ready gitnexus; then return; fi
    if [[ "$SCOPE" != repo ]]; then
        echo "GitNexus: install global npm package"
        if ((DRY_RUN)); then
            print_cmd npm install -g gitnexus@latest
            GITNEXUS=gitnexus
            return
        elif npm install -g gitnexus@latest; then
            GITNEXUS="$(global_tool gitnexus)"
            return
        elif [[ "$SCOPE" != auto ]]; then
            return 1
        fi
        warn "global GitNexus install failed; falling back to the repository"
    fi
    echo "GitNexus: install npm package in .agent-tools"
    run npm install --prefix "$ROOT/.agent-tools/gitnexus" gitnexus@latest
    if ((DRY_RUN)); then
        GITNEXUS="$ROOT/.agent-tools/bin/gitnexus"
    else
        mkdir -p .agent-tools/bin
        ln -sf "$ROOT/.agent-tools/gitnexus/node_modules/.bin/gitnexus" .agent-tools/bin/gitnexus
        GITNEXUS="$ROOT/.agent-tools/bin/gitnexus"
    fi
}

install_graphify() {
    if tool_ready graphify; then return; fi
    if [[ "$SCOPE" != repo ]]; then
        echo "Graphify: install user-global Python tool"
        if ((DRY_RUN)); then
            if command -v uv >/dev/null 2>&1; then
                print_cmd uv tool install graphifyy
            else
                print_cmd python3 -m pip install --user graphifyy
            fi
            GRAPHIFY=graphify
            return
        elif command -v uv >/dev/null 2>&1 && uv tool install graphifyy; then
            GRAPHIFY="$(global_tool graphify)"
            return
        elif ! command -v uv >/dev/null 2>&1 && python3 -m pip install --user graphifyy; then
            GRAPHIFY="$(global_tool graphify)"
            return
        elif [[ "$SCOPE" != auto ]]; then
            return 1
        fi
        warn "global Graphify install failed; falling back to the repository"
    fi
    echo "Graphify: install isolated environment in .agent-tools"
    if command -v uv >/dev/null 2>&1; then
        run uv venv "$ROOT/.agent-tools/graphify"
        run uv pip install --python "$ROOT/.agent-tools/graphify/bin/python" graphifyy
    else
        run python3 -m venv "$ROOT/.agent-tools/graphify"
        run "$ROOT/.agent-tools/graphify/bin/python" -m pip install graphifyy
    fi
    if ((DRY_RUN)); then
        GRAPHIFY="$ROOT/.agent-tools/bin/graphify"
    else
        mkdir -p .agent-tools/bin
        ln -sf "$ROOT/.agent-tools/graphify/bin/graphify" .agent-tools/bin/graphify
        GRAPHIFY="$ROOT/.agent-tools/bin/graphify"
    fi
}

validate_graphify_scope() {
    if ((DRY_RUN)); then
        echo "Graphify: validate .graphifyignore yields zero code files"
        return
    fi
    local python_bin
    python_bin="$(head -1 "$GRAPHIFY" | sed 's/^#!//; s/ -E$//')"
    "$python_bin" - <<'PY'
from pathlib import Path
from graphify.detect import detect

result = detect(Path("."))
code = result.get("files", {}).get("code", [])
if code:
    raise SystemExit(f"Graphify knowledge scope leaked {len(code)} code files")
print(f"Graphify knowledge corpus: {result['total_files']} files, 0 code files")
PY
}

legacy_graphify_contains_code() {
    python3 - <<'PY'
import json
import sys
from pathlib import Path

code_suffixes = {
    ".c", ".cc", ".cpp", ".cs", ".dart", ".go", ".h", ".hpp",
    ".java", ".js", ".jsx", ".kt", ".kts", ".lua", ".m", ".mm",
    ".php", ".py", ".r", ".rb", ".rs", ".scala", ".sh", ".swift",
    ".ts", ".tsx", ".vue",
}
found = []
for graph_path in (Path("graphify-out/graph.json"), Path("src/graphify-out/graph.json")):
    if not graph_path.is_file():
        continue
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: cannot classify {graph_path}: {exc}", file=sys.stderr)
        continue
    for node in graph.get("nodes", []):
        file_type = str(node.get("file_type") or node.get("type") or "").lower()
        source = str(
            node.get("source_file")
            or node.get("sourceFile")
            or node.get("path")
            or ""
        )
        if file_type == "code" or Path(source).suffix.lower() in code_suffixes:
            found.append((graph_path, source or str(node.get("id") or node.get("label") or "<code node>")))
            break

if found:
    for graph_path, source in found:
        print(f"Legacy Graphify code reference: {graph_path} -> {source}")
    raise SystemExit(0)
raise SystemExit(1)
PY
}

remove_graphify_codex_hook() {
    local hooks_file="$ROOT/.codex/hooks.json"
    [[ -f "$hooks_file" ]] || return 0
    if ((DRY_RUN)); then
        echo "Graphify cleanup: remove Graphify entries from .codex/hooks.json"
        return
    fi
    python3 - "$hooks_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(f"warning: preserving unreadable {path}: {exc}", file=sys.stderr)
    raise SystemExit(0)

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    raise SystemExit(0)
entries = hooks.get("PreToolUse")
if not isinstance(entries, list):
    raise SystemExit(0)
filtered = []
for entry in entries:
    if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
        filtered.append(entry)
        continue
    remaining = [
        hook for hook in entry["hooks"] if "graphify" not in str(hook).lower()
    ]
    if remaining:
        filtered.append({**entry, "hooks": remaining})
if filtered == entries:
    raise SystemExit(0)
if filtered:
    hooks["PreToolUse"] = filtered
else:
    hooks.pop("PreToolUse", None)
if not hooks:
    data.pop("hooks", None)
if data:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
else:
    path.unlink()
PY
    rmdir "$ROOT/.codex" 2>/dev/null || true
}

remove_graphify_git_hooks() {
    local hooks_dir
    hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null || true)"
    [[ -n "$hooks_dir" ]] || return
    [[ "$hooks_dir" = /* ]] || hooks_dir="$ROOT/$hooks_dir"
    if ((DRY_RUN)); then
        echo "Graphify cleanup: remove marked blocks from post-commit/post-checkout hooks"
        return
    fi
    python3 - "$hooks_dir" <<'PY'
import re
import sys
from pathlib import Path

hooks_dir = Path(sys.argv[1])
markers = {
    "post-commit": ("# graphify-hook-start", "# graphify-hook-end"),
    "post-checkout": ("# graphify-checkout-hook-start", "# graphify-checkout-hook-end"),
}
for name, (start, end) in markers.items():
    path = hooks_dir / name
    if not path.is_file():
        continue
    content = path.read_text(encoding="utf-8")
    if start not in content:
        continue
    cleaned = re.sub(
        rf"{re.escape(start)}.*?{re.escape(end)}\n?",
        "",
        content,
        flags=re.DOTALL,
    ).strip()
    if not cleaned or cleaned in {"#!/bin/bash", "#!/bin/sh"}:
        path.unlink()
    else:
        path.write_text(cleaned + "\n", encoding="utf-8")
PY
}

cleanup_legacy_graphify() {
    if ! legacy_graphify_contains_code; then
        return
    fi
    echo "Graphify cleanup: verified legacy code graph; removing generated collateral"
    remove_graphify_codex_hook
    remove_graphify_git_hooks
    if ((DRY_RUN)); then
        print_cmd rm -rf "$ROOT/graphify-out" "$ROOT/src/graphify-out"
    else
        rm -rf "$ROOT/graphify-out" "$ROOT/src/graphify-out"
    fi
}

cleanup_legacy_graphify
if ((CLEANUP_ONLY)); then
    echo "Graphify legacy cleanup complete."
    exit 0
fi

install_codegraph
install_gitnexus
install_graphify

CODEGRAPH="${CODEGRAPH:-$(selected_tool codegraph)}"
GITNEXUS="${GITNEXUS:-$(selected_tool gitnexus)}"
GRAPHIFY="${GRAPHIFY:-$(selected_tool graphify)}"

if ((CONFIGURE)); then
    if [[ "$CODEGRAPH" != "$ROOT/.agent-tools/bin/codegraph" ]]; then
        run "$CODEGRAPH" install --target=codex --location=global --yes
    else
        warn "CodeGraph's Codex installer has no project-local mode; AGENTS.local.md uses the local CLI fallback"
    fi
    if [[ "$GITNEXUS" != "$ROOT/.agent-tools/bin/gitnexus" ]]; then
        run "$GITNEXUS" setup -c codex
    else
        warn "GitNexus MCP was not configured globally; AGENTS.local.md uses the local CLI fallback"
    fi
    if [[ "$GRAPHIFY" == "$ROOT/.agent-tools/bin/graphify" ]]; then
        run "$GRAPHIFY" install --project --platform codex
    else
        run "$GRAPHIFY" install --platform codex
    fi
fi

if ((INDEX)); then
    [[ -f .codegraph/codegraph.db ]] || run "$CODEGRAPH" init "$ROOT"
    run "$GITNEXUS" analyze "$ROOT" --skip-agents-md --skip-skills
    if [[ -n "${GRAPHIFY_BOOTSTRAP_BACKEND:-}" ]]; then
        validate_graphify_scope
        run "$GRAPHIFY" extract "$ROOT" --backend "$GRAPHIFY_BOOTSTRAP_BACKEND" --out "$ROOT"
    elif [[ ! -f graphify-out/graph.json ]]; then
        warn "Graphify knowledge graph not built; run /graphify . or set GRAPHIFY_BOOTSTRAP_BACKEND"
    fi
fi

echo "Knowledge-graph bootstrap complete."
echo "Restart Codex after a real run so newly configured MCP servers are loaded."
