#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$REPO_ROOT/tmp"
mkdir -p "$TMP_DIR"

usage() {
  cat <<'EOF'
Usage:
  bin/confluence-workflow.sh doctor
  bin/confluence-workflow.sh health
  bin/confluence-workflow.sh export-page <PAGE_ID> [OUTPUT_DIR]

Commands:
  doctor      Run local auth/git diagnostics and write a timestamped log in tmp/
  health      Call Confluence API health check via the CLI
  export-page Export one Confluence page to JSON

Environment required for API calls:
  CONFLUENCE_BASE_URL
  CONFLUENCE_API_TOKEN
EOF
}

ensure_cli() {
  if ! command -v confluence-export >/dev/null 2>&1; then
    echo "confluence-export CLI not found."
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
  fi
}

doctor() {
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local log_file="$TMP_DIR/doctor-$ts.log"

  {
    echo "[start] $(date -u +%FT%TZ)"
    echo "repo=$REPO_ROOT"
    echo "--- gh auth status ---"
    GH_PAGER=cat gh auth status || true
    echo "--- gh user ---"
    GH_PAGER=cat gh api user -q .login || true
    echo "--- git remotes ---"
    git -C "$REPO_ROOT" remote -v || true
    echo "--- git branch/status ---"
    git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD || true
    git -C "$REPO_ROOT" status -sb || true
    echo "--- push dry-run ---"
    git -C "$REPO_ROOT" push --dry-run origin main || true
    echo "[end] $(date -u +%FT%TZ)"
  } > "$log_file" 2>&1

  echo "$log_file"
}

health() {
  ensure_cli
  confluence-export health
}

export_page() {
  ensure_cli
  local page_id="$1"
  local output_dir="${2:-$REPO_ROOT/exports}"
  confluence-export export-page --page-id "$page_id" --output "$output_dir"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    doctor)
      shift
      doctor "$@"
      ;;
    health)
      shift
      health "$@"
      ;;
    export-page)
      shift
      if [[ $# -lt 1 ]]; then
        echo "Missing PAGE_ID"
        usage
        exit 2
      fi
      export_page "$@"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Unknown command: $cmd"
      usage
      exit 2
      ;;
  esac
}

main "$@"
