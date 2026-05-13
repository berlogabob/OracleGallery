#!/bin/zsh

set -e
setopt pipefail

SCRIPT_DIR="${0:A:h}"
LOCAL_ENV="$SCRIPT_DIR/oracle_uploader.local.env"

source_if_exists() {
  local profile_file="$1"
  if [[ -f "$profile_file" ]]; then
    local original_path="$PATH"
    set +e
    source "$profile_file" >/dev/null 2>&1
    set -e
    if ! command -v tr >/dev/null 2>&1 || ! command -v mv >/dev/null 2>&1; then
      PATH="$original_path"
    fi
  fi
}

pause() {
  echo
  read '?Press Enter to close...'
}

fail() {
  echo
  echo "ERROR: $1"
  pause
  exit 1
}

find_repo_dir() {
  if [[ -n "${ORACLE_REPO_DIR:-}" && -f "$ORACLE_REPO_DIR/pyproject.toml" && -d "$ORACLE_REPO_DIR/src/neje_oracle" ]]; then
    echo "$ORACLE_REPO_DIR"
    return 0
  fi

  local current="$SCRIPT_DIR"
  while [[ "$current" != "/" ]]; do
    if [[ -f "$current/pyproject.toml" && -d "$current/src/neje_oracle" ]]; then
      echo "$current"
      return 0
    fi
    current="${current:h}"
  done

  local default_repo="/Users/berloga/Documents/GitHub/NejeDraw"
  if [[ -f "$default_repo/pyproject.toml" && -d "$default_repo/src/neje_oracle" ]]; then
    echo "$default_repo"
    return 0
  fi

  return 1
}

find_uv() {
  local discovered
  discovered="$(command -v uv 2>/dev/null || true)"
  local -a candidates=(
    "$discovered"
    "/opt/homebrew/bin/uv"
    "/usr/local/bin/uv"
    "$HOME/.local/bin/uv"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

upsert_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp)"
  touch "$file"
  UPSERT_VALUE="$value" awk -v key="$key" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" {
      if (!found) {
        print key "=" ENVIRON["UPSERT_VALUE"]
        found = 1
      }
      next
    }
    { print }
    END {
      if (!found) {
        print key "=" ENVIRON["UPSERT_VALUE"]
      }
    }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

ensure_gitignore_line() {
  local file="$1"
  local line="$2"
  touch "$file"
  grep -qxF "$line" "$file" 2>/dev/null || echo "$line" >> "$file"
}

source_if_exists "$HOME/.zprofile"
source_if_exists "$HOME/.zshrc"
source_if_exists "$HOME/.bash_profile"
source_if_exists "$HOME/.profile"
source_if_exists "$LOCAL_ENV"

REPO_DIR="$(find_repo_dir)" || fail "Cannot find Oracle project. Put this sessions folder inside the repo or set ORACLE_REPO_DIR in $LOCAL_ENV."
UV_BIN="$(find_uv)" || fail "uv was not found. Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
ENV_FILE="$REPO_DIR/.env"
GITIGNORE_FILE="$REPO_DIR/.gitignore"

FIREBASE_PROJECT_ID="${NEJE_FIREBASE_PROJECT_ID:-oraclegallery}"
FIREBASE_STORAGE_BUCKET="${NEJE_FIREBASE_STORAGE_BUCKET:-oraclegallery.firebasestorage.app}"
FIREBASE_CREDENTIALS="${NEJE_FIREBASE_CREDENTIALS:-$REPO_DIR/secrets/oraclegallery-firebase-adminsdk.json}"
GALLERY_BASE_URL="${NEJE_GALLERY_BASE_URL:-https://berlogabob.github.io/OracleGallery}"

mkdir -p "$REPO_DIR/runtime" "$REPO_DIR/sessions_public"
ensure_gitignore_line "$GITIGNORE_FILE" ".env"
ensure_gitignore_line "$GITIGNORE_FILE" "secrets/"
ensure_gitignore_line "$GITIGNORE_FILE" "runtime/"
ensure_gitignore_line "$GITIGNORE_FILE" "sessions_public/"
ensure_gitignore_line "$GITIGNORE_FILE" "*.sqlite3"
ensure_gitignore_line "$GITIGNORE_FILE" "*.log"

cat > "$LOCAL_ENV" <<EOF
ORACLE_REPO_DIR=$REPO_DIR
EOF

upsert_env "$ENV_FILE" "NEJE_FIREBASE_PROJECT_ID" "$FIREBASE_PROJECT_ID"
upsert_env "$ENV_FILE" "NEJE_FIREBASE_STORAGE_BUCKET" "$FIREBASE_STORAGE_BUCKET"
upsert_env "$ENV_FILE" "NEJE_FIREBASE_CREDENTIALS" "$FIREBASE_CREDENTIALS"
upsert_env "$ENV_FILE" "NEJE_GALLERY_BASE_URL" "$GALLERY_BASE_URL"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_SESSION_ROOT" "$SCRIPT_DIR"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_PUBLIC_ROOT" "$REPO_DIR/sessions_public"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_DB_PATH" "$REPO_DIR/runtime/uploader.sqlite3"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_REQUIRE_READY_MARKER" "false"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_STABILITY_SECONDS" "8"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_POLL_SECONDS" "2"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_AGENT_HOST" "0.0.0.0"
upsert_env "$ENV_FILE" "NEJE_UPLOADER_AGENT_PORT" "8790"

clear || true
echo "========================================"
echo "  Oracle Mac mini Uploader"
echo "========================================"
echo "Sessions folder: $SCRIPT_DIR"
echo "Project folder:  $REPO_DIR"
echo "Config file:     $ENV_FILE"
echo "Agent:           http://0.0.0.0:8790/"
echo

if [[ ! -f "$FIREBASE_CREDENTIALS" ]]; then
  echo "WARNING: Firebase service account file not found:"
  echo "$FIREBASE_CREDENTIALS"
  echo "Put the JSON key there or edit NEJE_FIREBASE_CREDENTIALS in $ENV_FILE."
  echo
fi

cd "$REPO_DIR"
"$UV_BIN" sync --extra dev || fail "Dependency setup failed."

set -a
source "$ENV_FILE"
set +a

[[ -f "$NEJE_FIREBASE_CREDENTIALS" ]] || fail "NEJE_FIREBASE_CREDENTIALS points to a missing file: $NEJE_FIREBASE_CREDENTIALS"
[[ -d "$NEJE_UPLOADER_SESSION_ROOT" ]] || fail "NEJE_UPLOADER_SESSION_ROOT points to a missing folder: $NEJE_UPLOADER_SESSION_ROOT"
mkdir -p "$NEJE_UPLOADER_PUBLIC_ROOT" || fail "Cannot create NEJE_UPLOADER_PUBLIC_ROOT: $NEJE_UPLOADER_PUBLIC_ROOT"

echo "Starting uploader agent only."
echo "The Mac mini must not run generators, GUI, or plotter launchers during exhibition."
echo

"$UV_BIN" run neje-uploader-agent
exit_code=$?

echo
echo "Oracle Mac mini Uploader stopped with exit code $exit_code."
pause
exit "$exit_code"
