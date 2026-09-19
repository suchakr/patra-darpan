#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$ROOT_DIR/web"
PROJECT_NAME="Patra Darpan semantic-index checkout"
PUBLISH_DIR="."
FUNCTIONS_DIR="netlify/functions"
EXPECTED_SITE_ID=""
DEFAULT_PORT="8900"
PORT_BLOCK_SIZE="10"

usage() {
  cat <<EOF
Usage: ./deploy.sh [--dev|--stage|--prod] [options] [-- netlify-args...]

Modes:
  --dev, dev        Start Netlify Dev. Uses this project's reserved port block.
  --stage, stage    Create a draft/preview deployment (default).
  --prod, prod      Deploy to production after confirmation.
  --help, -h        Show this help without contacting Netlify.

Options:
  -p, --port PORT   Preferred public port (default: 8900).
  --static-port N   Preferred internal static-server port (default: PORT + 1).
  -n, --dry-run     Print resolved commands without executing them.
  -y, --yes         Skip the production confirmation.
  --                Pass all remaining arguments directly to Netlify CLI.

Reserved block: 8900-$(( 8900 + 9 ))
Publish path: .
Examples:
  ./deploy.sh --dev
  ./deploy.sh --stage
  ./deploy.sh --prod
  ./deploy.sh --dev --port 8900
  ./deploy.sh --stage -- --message "preview"
EOF
}

mode=""
port="$DEFAULT_PORT"
static_port=""
dry_run=0
assume_yes=0
passthrough=()

set_mode() {
  local requested="$1"
  if [[ -n "$mode" && "$mode" != "$requested" ]]; then
    echo "Choose exactly one mode; received --$mode and --$requested." >&2
    exit 2
  fi
  mode="$requested"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev|dev|--local|local)
      set_mode dev
      shift
      ;;
    --stage|stage)
      set_mode stage
      shift
      ;;
    --prod|prod)
      set_mode prod
      shift
      ;;
    -p|--port)
      [[ $# -ge 2 && "$2" != -* ]] || { echo "Missing port after $1." >&2; exit 2; }
      port="$2"
      shift 2
      ;;
    --static-port|--static-server-port|--staticServerPort|--target-port)
      [[ $# -ge 2 && "$2" != -* ]] || { echo "Missing static port after $1." >&2; exit 2; }
      static_port="$2"
      shift 2
      ;;
    -n|--dry-run)
      dry_run=1
      shift
      ;;
    -y|--yes)
      assume_yes=1
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
      echo "Unknown wrapper option: $1" >&2
      echo "Put raw Netlify arguments after --." >&2
      exit 2
      ;;
  esac
done

mode="${mode:-stage}"

valid_port() {
  [[ "$1" =~ ^[0-9]+$ && "$1" -ge 1 && "$1" -le 65535 ]]
}
valid_port "$port" || { echo "Invalid public port: $port" >&2; exit 2; }
if [[ -n "$static_port" ]]; then
  valid_port "$static_port" || { echo "Invalid static port: $static_port" >&2; exit 2; }
fi

resolve_netlify() {
  if command -v netlify >/dev/null 2>&1; then
    NETLIFY=(netlify)
  elif [[ -x "$WORK_DIR/node_modules/.bin/netlify" ]]; then
    NETLIFY=("$WORK_DIR/node_modules/.bin/netlify")
  elif [[ -x "$ROOT_DIR/node_modules/.bin/netlify" ]]; then
    NETLIFY=("$ROOT_DIR/node_modules/.bin/netlify")
  else
    echo "Netlify CLI not found. Install it globally or in this project." >&2
    exit 1
  fi
}

listener_for() {
  command -v lsof >/dev/null 2>&1 || return 0
  lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | sed -n '2p' || true
}

port_busy() {
  local candidate="$1"
  if command -v lsof >/dev/null 2>&1 &&
     lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  if command -v nc >/dev/null 2>&1 &&
     nc -z 127.0.0.1 "$candidate" >/dev/null 2>&1; then
    return 0
  fi
  if command -v nc >/dev/null 2>&1 &&
     nc -z ::1 "$candidate" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

report_conflict() {
  local candidate="$1"
  local listener
  listener="$(listener_for "$candidate")"
  if [[ -n "$listener" ]]; then
    printf 'Port %s is occupied: %s\n' "$candidate" "$listener" >&2
  else
    printf 'Port %s is occupied.\n' "$candidate" >&2
  fi
}

choose_port_pair() {
  local candidate="$port"
  local limit=$((port + PORT_BLOCK_SIZE))
  if [[ -n "$static_port" ]]; then
    if port_busy "$port"; then report_conflict "$port"; return 1; fi
    if [[ "$static_port" == "$port" ]]; then
      echo "Public and static ports must differ." >&2
      return 1
    fi
    if port_busy "$static_port"; then report_conflict "$static_port"; return 1; fi
    chosen_port="$port"
    chosen_static_port="$static_port"
    return 0
  fi
  while [[ $((candidate + 1)) -lt "$limit" && $((candidate + 1)) -le 65535 ]]; do
    if ! port_busy "$candidate" && ! port_busy "$((candidate + 1))"; then
      chosen_port="$candidate"
      chosen_static_port="$((candidate + 1))"
      return 0
    fi
    port_busy "$candidate" && report_conflict "$candidate"
    port_busy "$((candidate + 1))" && report_conflict "$((candidate + 1))"
    candidate=$((candidate + 2))
  done
  echo "No free port pair in this project's block: $port-$((limit - 1))." >&2
  return 1
}

print_command() {
  printf 'Resolved command:'
  printf ' %q' "$@"
  printf '\n'
}

run_in_workdir() {
  printf 'Project: %s\n' "$PROJECT_NAME"
  printf 'Working directory: %s\n' "$WORK_DIR"
  print_command "$@"
  if [[ "$dry_run" -eq 0 ]]; then
    (cd "$WORK_DIR" && "$@")
  fi
}

verify_site_link() {
  local state_file="$WORK_DIR/.netlify/state.json"
  if [[ ! -f "$state_file" ]]; then
    echo "Refusing remote deployment: this app is not linked to a Netlify site." >&2
    echo "Run 'cd $WORK_DIR && netlify link', verify the site, then retry." >&2
    exit 1
  fi
  local linked_id
  linked_id="$(sed -nE 's/.*"siteId"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$state_file" | head -1)"
  if [[ -z "$linked_id" ]]; then
    echo "Refusing remote deployment: $state_file contains no siteId." >&2
    exit 1
  fi
  if [[ -n "$EXPECTED_SITE_ID" && "$linked_id" != "$EXPECTED_SITE_ID" ]]; then
    echo "Refusing remote deployment: linked Netlify site does not match this wrapper." >&2
    exit 1
  fi
  echo "Netlify site link verified."
}

deploy_args=(deploy --dir "$PUBLISH_DIR")
if [[ -n "$FUNCTIONS_DIR" ]]; then
  deploy_args+=(--functions "$FUNCTIONS_DIR")
fi

case "$mode" in
  dev)
    resolve_netlify
    choose_port_pair
    if [[ "$chosen_port" != "$port" ]]; then
      echo "Preferred pair is occupied; using $chosen_port/$chosen_static_port within the reserved block."
    fi
    echo "Local URL: http://127.0.0.1:$chosen_port/"
    run_in_workdir "${NETLIFY[@]}" dev --dir "$PUBLISH_DIR" \
      --port "$chosen_port" --staticServerPort "$chosen_static_port" \
      "${passthrough[@]}"
    ;;
  stage)
    resolve_netlify
    verify_site_link
    run_in_workdir "${NETLIFY[@]}" "${deploy_args[@]}" "${passthrough[@]}"
    ;;
  prod)
    resolve_netlify
    verify_site_link
    if [[ "$assume_yes" -eq 0 && "$dry_run" -eq 0 ]]; then
      read -r -p "Deploy $PROJECT_NAME to production? [y/N] " reply
      [[ "$reply" =~ ^[Yy]$ ]] || { echo "Production deployment cancelled."; exit 0; }
    fi
    run_in_workdir "${NETLIFY[@]}" "${deploy_args[@]}" --prod "${passthrough[@]}"
    ;;
esac

