#!/bin/zsh

setopt pipefail

SCRIPT_DIR="${0:A:h}"
LOCAL_ENV="$SCRIPT_DIR/oracle_uploader.local.env"

source_if_exists() {
  local profile_file="$1"
  if [[ -f "$profile_file" ]]; then
    local original_path="$PATH"
    source "$profile_file" >/dev/null 2>&1 || true
    if ! command -v tr >/dev/null 2>&1 || ! command -v mv >/dev/null 2>&1; then
      PATH="$original_path"
    fi
  fi
}

fail_before_common() {
  echo
  echo "ERROR: $1"
  echo
  read '?Press Enter to close...'
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

source_if_exists "$HOME/.zprofile"
source_if_exists "$HOME/.zshrc"
source_if_exists "$HOME/.bash_profile"
source_if_exists "$HOME/.profile"
source_if_exists "$LOCAL_ENV"

REPO_DIR="$(find_repo_dir)" || fail_before_common "Cannot find OracleGallery project. Run SETUP_ORACLE_UPLOADER.command first or set ORACLE_REPO_DIR in $LOCAL_ENV."

source "$REPO_DIR/scripts/launcher_common.sh" || fail_before_common "Cannot load launcher helper from $REPO_DIR."
launcher_bootstrap "Oracle Firebase Uploader" "$REPO_DIR"

export NEJE_UPLOADER_SESSION_ROOT="$SCRIPT_DIR"

launcher_require_var "NEJE_FIREBASE_PROJECT_ID" "Run SETUP_ORACLE_UPLOADER.command first."
launcher_require_var "NEJE_FIREBASE_STORAGE_BUCKET" "Run SETUP_ORACLE_UPLOADER.command first."
launcher_require_existing_file_var "NEJE_FIREBASE_CREDENTIALS" "Point this to your Firebase service account JSON in $REPO_DIR/.env."
launcher_require_var "NEJE_GALLERY_BASE_URL" "Run SETUP_ORACLE_UPLOADER.command first."
launcher_require_existing_dir_var "NEJE_UPLOADER_SESSION_ROOT" "This should be the TouchDesigner sessions folder."
launcher_ensure_dir_var "NEJE_UPLOADER_PUBLIC_ROOT" "Run SETUP_ORACLE_UPLOADER.command first."

echo "Watching:   $NEJE_UPLOADER_SESSION_ROOT"
echo "Publishing: $NEJE_UPLOADER_PUBLIC_ROOT"
echo "Gallery:    $NEJE_GALLERY_BASE_URL"
echo

launcher_run_service "neje-uploader"
