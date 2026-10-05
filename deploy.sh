#!/usr/bin/env bash
set -euo pipefail

# Deployment policy: corpus/GCS validity is enforced; Git cleanliness is
# advisory unless production is invoked with --strict.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$ROOT_DIR/web"
EXPECTED_SITE_ID="${PATRA_DARPAN_NETLIFY_SITE_ID:-27e273a3-bc69-4619-b387-9cc64bbc0563}"
DEFAULT_PORT="8890"
DEFAULT_STATIC_SERVER_PORT="8891"
PORT_BLOCK_SIZE="10"

usage() {
  cat <<'EOF'
Usage:
  ./deploy.sh [prepare|gcs-sync|stage|prod|local] [options] [-- netlify args...]

Modes:
  prepare                 Rebuild, validate, and report GCS drift.
  gcs-sync                Explicitly upload pending corpus PDFs to GCS.
  stage, --stage          Create a Netlify preview deploy. Default mode.
  prod, --prod            Deploy the current web snapshot to production.
  local, --local          Start the local Netlify development server.
  dev, --dev              Alias for local.

Options:
  --strict                For prod, require clean main branch.
  -p, --port PORT         Local Netlify URL port. Default: 8890.
  --static-port PORT      Local static-server port. Default: 8891.
  -y, --yes               Bypass wrapper confirmations.
  -n, --dry-run           Print resolved commands without running them.
  -h, --help              Show this help.

Examples:
  ./deploy.sh prepare
  ./deploy.sh gcs-sync
  ./deploy.sh --dev --port 8894 --static-port 8895
  ./deploy.sh stage -- --message "corpus preview"
  ./deploy.sh prod
  ./deploy.sh prod --strict
EOF
}

mode="stage"
port="$DEFAULT_PORT"
static_server_port="$DEFAULT_STATIC_SERVER_PORT"
strict=0
assume_yes=0
dry_run=0
passthrough=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    prepare)
      mode="prepare"
      shift
      ;;
    gcs-sync|gcs)
      mode="gcs-sync"
      shift
      ;;
    prod|--prod)
      mode="prod"
      shift
      ;;
    stage|--stage)
      mode="stage"
      shift
      ;;
    local|--local|dev|--dev)
      mode="local"
      shift
      ;;
    --strict)
      strict=1
      shift
      ;;
    -p|--port)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Missing port after $1" >&2
        exit 2
      fi
      port="$2"
      shift 2
      ;;
    --static-port|--static-server-port|--target-port)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Missing port after $1" >&2
        exit 2
      fi
      static_server_port="$2"
      shift 2
      ;;
    -y|--yes)
      assume_yes=1
      shift
      ;;
    -n|--dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      passthrough=("$@")
      break
      ;;
    *)
      passthrough+=("$1")
      shift
      ;;
  esac
done

validate_port() {
  local value="$1"
  local label="$2"
  if [[ ! "$value" =~ ^[0-9]+$ || "$value" -lt 1 || "$value" -gt 65535 ]]; then
    echo "Invalid $label: $value" >&2
    exit 2
  fi
}

validate_port "$port" "port"
validate_port "$static_server_port" "static server port"

if [[ "$strict" -eq 1 && "$mode" != "prod" ]]; then
  echo "--strict is only valid with prod" >&2
  exit 2
fi

print_command() {
  printf 'Resolved command:'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  print_command "$@"
  if [[ "$dry_run" -eq 0 ]]; then
    "$@"
  fi
}

run_in_web() {
  printf 'Working directory: %s\n' "$WEB_DIR"
  print_command "$@"
  if [[ "$dry_run" -eq 0 ]]; then
    (cd "$WEB_DIR" && "$@")
  fi
}

confirm() {
  local prompt="$1"
  if [[ "$assume_yes" -eq 1 || "$dry_run" -eq 1 ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

resolve_netlify() {
  if command -v netlify >/dev/null 2>&1; then
    NETLIFY=(netlify)
  elif [[ -x "$WEB_DIR/node_modules/.bin/netlify" ]]; then
    NETLIFY=("$WEB_DIR/node_modules/.bin/netlify")
  else
    echo "Netlify CLI not found. Run npm install in web/ or install netlify-cli." >&2
    exit 1
  fi
}

git_snapshot() {
  branch="$(git -C "$ROOT_DIR" branch --show-current)"
  [[ -n "$branch" ]] || branch="detached"
  short_sha="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
  changed_count="$(git -C "$ROOT_DIR" status --porcelain | wc -l | tr -d ' ')"
  if [[ "$changed_count" -gt 0 ]]; then
    worktree_state="DIRTY ($changed_count paths)"
    deploy_suffix="+dirty"
  else
    worktree_state="clean"
    deploy_suffix=""
  fi
  printf 'Branch: %s\n' "$branch"
  printf 'HEAD: %s\n' "$short_sha"
  printf 'Worktree: %s\n' "$worktree_state"
}

set_deploy_message() {
  local default_message="$1"
  local arg
  deploy_message_args=(--message "$default_message")
  for arg in "${passthrough[@]}"; do
    case "$arg" in
      -m|--message|--message=*)
        deploy_message_args=()
        return 0
        ;;
    esac
  done
}

enforce_strict_git() {
  if [[ "$branch" != "main" ]]; then
    echo "Strict production deploy requires branch main; found $branch." >&2
    exit 1
  fi
  if [[ "$changed_count" -gt 0 ]]; then
    echo "Strict production deploy requires a clean worktree." >&2
    exit 1
  fi
}

ensure_site_link() {
  local state_file="$WEB_DIR/.netlify/state.json"
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'Expected Netlify site: %s\n' "$EXPECTED_SITE_ID"
    return 0
  fi
  if [[ ! -f "$state_file" ]]; then
    echo "Netlify site is not linked in web/. Run 'cd web && netlify link'." >&2
    exit 1
  fi
  if ! grep -Eq "\"siteId\"[[:space:]]*:[[:space:]]*\"$EXPECTED_SITE_ID\"" "$state_file"; then
    echo "Refusing deploy: web/ is linked to an unexpected Netlify site." >&2
    echo "Expected site ID: $EXPECTED_SITE_ID" >&2
    exit 1
  fi
  printf 'Netlify site: %s\n' "$EXPECTED_SITE_ID"
}

web_syntax_check() {
  run node --check "$WEB_DIR/assets/js/app.js"
  run node --check "$WEB_DIR/assets/js/data.js"
  run node --check "$WEB_DIR/assets/js/p60.js"
  run node --check "$WEB_DIR/assets/js/mcp-explorer-core.js"
  run node --check "$WEB_DIR/assets/js/mcp-explorer.js"
  run python3 "$ROOT_DIR/ops/export_mcp_explorer.py" --check
}

port_is_busy() {
  local check_port="$1"
  if command -v lsof >/dev/null 2>&1 &&
     lsof -nP -iTCP:"$check_port" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  if command -v nc >/dev/null 2>&1 &&
     nc -z 127.0.0.1 "$check_port" >/dev/null 2>&1; then
    return 0
  fi
  if command -v nc >/dev/null 2>&1 &&
     nc -z ::1 "$check_port" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

find_open_port() {
  local candidate="$1"
  local excluded="${2:-0}"
  local limit=$((candidate + PORT_BLOCK_SIZE))
  while [[ "$candidate" -le 65535 && "$candidate" -lt "$limit" ]]; do
    if [[ "$candidate" -ne "$excluded" ]] && ! port_is_busy "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
    candidate=$((candidate + 1))
  done
  echo "No open port found near $1" >&2
  return 1
}

prepare() {
  run uv run python "$ROOT_DIR/scripts/build_corpus_metadata.py"
  run uv run python "$ROOT_DIR/scripts/export_index_tsv.py"
  run uv run python "$ROOT_DIR/scripts/validate_legacy_index.py"
  run uv run python "$ROOT_DIR/scripts/audit_corpus_inputs.py"
  run uv run python "$ROOT_DIR/ops/export_patra_darpan_data_js.py"
  run python3 "$ROOT_DIR/ops/export_mcp_explorer.py"
  web_syntax_check
  run uv run python "$ROOT_DIR/ops/sync_gcs.py" --diff
}

gcs_sync() {
  run uv run python "$ROOT_DIR/ops/sync_gcs.py" --diff
  if ! confirm "Upload all pending corpus PDFs to GCS?"; then
    echo "GCS upload cancelled."
    return 0
  fi
  run uv run python "$ROOT_DIR/ops/sync_gcs.py" -y
  run uv run python "$ROOT_DIR/ops/sync_gcs.py" --check
}

cd "$ROOT_DIR"

case "$mode" in
  prepare)
    prepare
    ;;
  gcs-sync)
    gcs_sync
    ;;
  local)
    run python3 "$ROOT_DIR/ops/export_mcp_explorer.py"
    resolve_netlify
    public_port="$(find_open_port "$port")"
    local_static_port="$(find_open_port "$static_server_port" "$public_port")"
    if [[ "$public_port" != "$port" ]]; then
      printf 'Port %s is busy; using %s for the local URL.\n' "$port" "$public_port"
    fi
    if [[ "$local_static_port" != "$static_server_port" ]]; then
      printf 'Static server port %s is busy; using %s.\n' \
        "$static_server_port" "$local_static_port"
    fi
    printf 'Local URL: http://127.0.0.1:%s/\n' "$public_port"
    run_in_web "${NETLIFY[@]}" dev --dir . --port "$public_port" \
      --staticServerPort "$local_static_port" "${passthrough[@]}"
    ;;
  stage)
    resolve_netlify
    git_snapshot
    set_deploy_message "$branch@$short_sha$deploy_suffix"
    ensure_site_link
    run python3 "$ROOT_DIR/ops/export_mcp_explorer.py"
    web_syntax_check
    run_in_web "${NETLIFY[@]}" deploy --dir . \
      "${deploy_message_args[@]}" "${passthrough[@]}"
    ;;
  prod)
    resolve_netlify
    git_snapshot
    set_deploy_message "$branch@$short_sha$deploy_suffix"
    if [[ "$strict" -eq 1 ]]; then
      enforce_strict_git
    elif [[ "$changed_count" -gt 0 || "$branch" != "main" ]]; then
      echo "Git state is advisory for this deploy; use --strict to enforce clean main."
    fi
    ensure_site_link
    run python3 "$ROOT_DIR/ops/export_mcp_explorer.py"
    web_syntax_check
    run uv run python "$ROOT_DIR/ops/sync_gcs.py" --check
    printf 'Target: Patra Darpan production\n'
    if ! confirm "Deploy this snapshot to production?"; then
      echo "Production deploy cancelled."
      exit 0
    fi
    run_in_web "${NETLIFY[@]}" deploy --dir . --prod \
      "${deploy_message_args[@]}" "${passthrough[@]}"
    ;;
esac
