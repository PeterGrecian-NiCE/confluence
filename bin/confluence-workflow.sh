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
  bin/confluence-workflow.sh export-space <SPACE_KEY> [OUTPUT_DIR] [MAX_PAGES]
  bin/confluence-workflow.sh export-cql "<CQL>" [OUTPUT_DIR] [MAX_PAGES]
  bin/confluence-workflow.sh build-contents [PAGES_DIR] [OUTPUT_FILE]

Commands:
  doctor      Run local auth/git diagnostics and write a timestamped log in tmp/
  health      Call Confluence API health check via the CLI
  export-page Export one Confluence page to JSON
  export-space Batch export all pages from a space to JSON + JSONL
  export-cql  Batch export pages matching custom CQL to JSON + JSONL
  build-contents Build a hierarchical markdown contents page from exported JSON

Environment required for API calls:
  CONFLUENCE_BASE_URL
  CONFLUENCE_API_TOKEN

Optional diagnostics variable:
  CONFLUENCE_TOKEN_EXPIRES_ON (YYYY-MM-DD)
EOF
}

resolve_cli() {
  if command -v confluence-export >/dev/null 2>&1; then
    command -v confluence-export
    return 0
  fi

  if [[ -x "$REPO_ROOT/.venv/bin/confluence-export" ]]; then
    echo "$REPO_ROOT/.venv/bin/confluence-export"
    return 0
  fi

  echo "confluence-export CLI not found." >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
  return 1
}

doctor() {
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local log_file="$TMP_DIR/doctor-$ts.log"
  local token=""
  local token_source=""

  if [[ -n "${CONFLUENCE_API_TOKEN:-}" ]]; then
    token="${CONFLUENCE_API_TOKEN}"
    token_source="CONFLUENCE_API_TOKEN"
  elif [[ -n "${ATLASSIAN_API_TOKEN:-}" ]]; then
    token="${ATLASSIAN_API_TOKEN}"
    token_source="ATLASSIAN_API_TOKEN"
  elif [[ -n "${CONFLUENCE_TOKEN:-}" ]]; then
    token="${CONFLUENCE_TOKEN}"
    token_source="CONFLUENCE_TOKEN"
  fi

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

    echo "--- confluence env ---"
    if [[ -n "${CONFLUENCE_BASE_URL:-}" ]]; then
      echo "base_url_set=true"
    else
      echo "base_url_set=false"
    fi
    if [[ -n "$token" ]]; then
      echo "token_set=true"
      echo "token_source=$token_source"
    else
      echo "token_set=false"
      echo "token_source=none"
    fi
    if [[ -n "${CONFLUENCE_EMAIL:-${ATLASSIAN_EMAIL:-${ATLASSIAN_USER_EMAIL:-}}}" ]]; then
      echo "email_set=true"
    else
      echo "email_set=false"
    fi

    echo "--- token expiry ---"
    if [[ -n "${CONFLUENCE_TOKEN_EXPIRES_ON:-}" ]]; then
      python3 - <<'PY'
import datetime
import os

value = os.getenv("CONFLUENCE_TOKEN_EXPIRES_ON", "").strip()
print(f"raw={value}")
try:
    exp = datetime.date.fromisoformat(value)
    today = datetime.datetime.utcnow().date()
    days_left = (exp - today).days
    print(f"days_left={days_left}")
    if days_left < 0:
        print("status=EXPIRED")
    elif days_left <= 2:
        print("status=CRITICAL")
    elif days_left <= 7:
        print("status=WARNING")
    else:
        print("status=OK")
except ValueError:
    print("status=INVALID_FORMAT (expected YYYY-MM-DD)")
PY
    else
      echo "status=UNKNOWN (set CONFLUENCE_TOKEN_EXPIRES_ON=YYYY-MM-DD)"
    fi

    echo "--- confluence api health probe ---"
    cli_path="$(resolve_cli 2>/dev/null || true)"
    if [[ -n "$cli_path" ]]; then
      if [[ -n "${CONFLUENCE_BASE_URL:-}" && -n "$token" ]]; then
        if probe_out=$("$cli_path" health 2>&1); then
          echo "api_health=ok"
          echo "$probe_out"
        else
          echo "api_health=fail"
          echo "$probe_out"
          if echo "$probe_out" | grep -Eqi '401|403|unauthoriz|not permitted|forbidden'; then
            echo "hint=auth failed: token may be expired/invalid or account lacks Confluence permissions"
          fi
        fi
      else
        echo "api_health=skipped (missing CONFLUENCE_BASE_URL or token env)"
      fi
    else
      echo "api_health=skipped (confluence-export CLI not installed)"
    fi

    echo "[end] $(date -u +%FT%TZ)"
  } > "$log_file" 2>&1

  echo "$log_file"
}

health() {
  local cli
  cli="$(resolve_cli)"
  "$cli" health
}

export_page() {
  local cli
  cli="$(resolve_cli)"
  local page_id="$1"
  local output_dir="${2:-$REPO_ROOT/exports}"
  "$cli" export-page --page-id "$page_id" --output "$output_dir"
}

export_space() {
  local cli
  cli="$(resolve_cli)"
  local space_key="$1"
  local output_dir="${2:-$REPO_ROOT/exports}"
  local max_pages="${3:-0}"
  "$cli" export-batch \
    --space-key "$space_key" \
    --output "$output_dir" \
    --max-pages "$max_pages"
}

export_cql() {
  local cli
  cli="$(resolve_cli)"
  local cql="$1"
  local output_dir="${2:-$REPO_ROOT/exports}"
  local max_pages="${3:-0}"
  "$cli" export-batch \
    --cql "$cql" \
    --output "$output_dir" \
    --max-pages "$max_pages"
}

build_contents() {
  local cli
  cli="$(resolve_cli)"
  local pages_dir=""
  if [[ $# -ge 1 && -n "${1:-}" ]]; then
    pages_dir="$1"
  else
    if [[ -d "$REPO_ROOT/exports/pages" ]]; then
      pages_dir="$REPO_ROOT/exports/pages"
    else
      pages_dir="$REPO_ROOT/exports"
    fi
  fi
  local output_file="${2:-$REPO_ROOT/exports/contents.md}"
  "$cli" build-contents \
    --input-pages-dir "$pages_dir" \
    --output "$output_file"
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
    export-space)
      shift
      if [[ $# -lt 1 ]]; then
        echo "Missing SPACE_KEY"
        usage
        exit 2
      fi
      export_space "$@"
      ;;
    export-cql)
      shift
      if [[ $# -lt 1 ]]; then
        echo "Missing CQL"
        usage
        exit 2
      fi
      export_cql "$@"
      ;;
    build-contents)
      shift
      build_contents "$@"
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
