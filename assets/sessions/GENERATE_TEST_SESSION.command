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
launcher_bootstrap "Oracle Test Session Generator" "$REPO_DIR"

export NEJE_UPLOADER_SESSION_ROOT="$SCRIPT_DIR"

echo "Generating one test user session in the real sessions folder."
echo "Output folder: $NEJE_UPLOADER_SESSION_ROOT"
echo "If START_ORACLE_UPLOADER.command is running, this will publish to Firebase and create a plot job."
echo

launcher_run_service "neje-generate-sessions" --mode user --count "${NEJE_GENERATOR_COUNT:-1}" --output-root "$SCRIPT_DIR"
