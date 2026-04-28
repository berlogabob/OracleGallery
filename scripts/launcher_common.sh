#!/bin/zsh

setopt pipefail

typeset -g LAUNCHER_NAME=""
typeset -g LAUNCHER_REPO_DIR=""
typeset -g LAUNCHER_UV_BIN=""

launcher_source_if_exists() {
  local profile_file="$1"
  if [[ -f "$profile_file" ]]; then
    local original_path="$PATH"
    source "$profile_file" >/dev/null 2>&1 || true
    if ! command -v tr >/dev/null 2>&1 || ! command -v mv >/dev/null 2>&1; then
      PATH="$original_path"
    fi
  fi
}

launcher_pause() {
  if [[ -t 0 ]]; then
    echo
    read '?Press Enter to close...'
  fi
}

launcher_fail() {
  local message="$1"
  echo
  echo "ERROR: $message"
  launcher_pause
  exit 1
}

launcher_find_uv() {
  local -a candidates
  local discovered

  discovered="$(command -v uv 2>/dev/null || true)"
  candidates=(
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

launcher_bootstrap() {
  LAUNCHER_NAME="$1"
  LAUNCHER_REPO_DIR="${2:-${0:A:h}}"

  cd "$LAUNCHER_REPO_DIR" || launcher_fail "Cannot open project folder: $LAUNCHER_REPO_DIR"

  launcher_source_if_exists "$HOME/.zprofile"
  launcher_source_if_exists "$HOME/.zshrc"
  launcher_source_if_exists "$HOME/.bash_profile"
  launcher_source_if_exists "$HOME/.profile"

  if [[ -f "$LAUNCHER_REPO_DIR/.env" ]]; then
    set -a
    source "$LAUNCHER_REPO_DIR/.env"
    set +a
  fi

  LAUNCHER_UV_BIN="$(launcher_find_uv)" || launcher_fail "uv was not found. Install uv first or add it to PATH."

  clear
  echo "========================================"
  echo "  $LAUNCHER_NAME"
  echo "========================================"
  echo "Project: $LAUNCHER_REPO_DIR"
  echo "uv:      $LAUNCHER_UV_BIN"
  echo
}

launcher_require_var() {
  local var_name="$1"
  local hint="$2"
  local value="${(P)var_name:-}"

  if [[ -z "$value" ]]; then
    launcher_fail "Missing $var_name. $hint"
  fi
}

launcher_require_existing_dir_var() {
  local var_name="$1"
  local hint="$2"
  launcher_require_var "$var_name" "$hint"

  local resolved_path="${(P)var_name}"
  if [[ ! -d "$resolved_path" ]]; then
    launcher_fail "$var_name points to a missing folder: $resolved_path"
  fi
}

launcher_require_existing_file_var() {
  local var_name="$1"
  local hint="$2"
  launcher_require_var "$var_name" "$hint"

  local resolved_path="${(P)var_name}"
  if [[ ! -f "$resolved_path" ]]; then
    launcher_fail "$var_name points to a missing file: $resolved_path"
  fi
}

launcher_ensure_dir_var() {
  local var_name="$1"
  local hint="$2"
  launcher_require_var "$var_name" "$hint"

  local resolved_path="${(P)var_name}"
  mkdir -p "$resolved_path" || launcher_fail "Cannot create folder for $var_name: $resolved_path"
}

launcher_require_svg_bank() {
  local var_name="$1"
  local hint="$2"
  launcher_require_existing_dir_var "$var_name" "$hint"

  local resolved_path="${(P)var_name}"
  local -a svg_files
  svg_files=("$resolved_path"/*.svg(N))
  if (( ${#svg_files} == 0 )); then
    launcher_fail "No placeholder SVG files found in $resolved_path"
  fi
}

launcher_run_service() {
  local service_name="$1"
  shift

  echo "Launching $service_name ..."
  echo

  "$LAUNCHER_UV_BIN" run "$service_name" "$@"
  local exit_code=$?

  echo
  if [[ $exit_code -eq 0 ]]; then
    echo "$LAUNCHER_NAME finished."
  else
    echo "$LAUNCHER_NAME stopped with exit code $exit_code."
  fi

  launcher_pause
  exit "$exit_code"
}
