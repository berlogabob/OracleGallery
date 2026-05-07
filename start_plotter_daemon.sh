#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Plotter Daemon" "$SCRIPT_DIR"

if [[ -z "${NEJE_PLOTTER_PLACEHOLDER_ROOT:-}" || "$NEJE_PLOTTER_PLACEHOLDER_ROOT" == "$SCRIPT_DIR/placeholders" ]]; then
  if [[ -d "$SCRIPT_DIR/assets/generated_idle_symbols" ]] && ls "$SCRIPT_DIR/assets/generated_idle_symbols"/*.svg >/dev/null 2>&1; then
    export NEJE_PLOTTER_PLACEHOLDER_ROOT="$SCRIPT_DIR/assets/generated_idle_symbols"
  else
    export NEJE_PLOTTER_PLACEHOLDER_ROOT="$SCRIPT_DIR/assets/symbols"
  fi
fi

launcher_require_var "NEJE_FIREBASE_PROJECT_ID" "Set it in .env on the MacBook."
launcher_require_var "NEJE_FIREBASE_STORAGE_BUCKET" "Set it in .env on the MacBook."
launcher_require_existing_file_var "NEJE_FIREBASE_CREDENTIALS" "Point this to your Firebase service account JSON."
launcher_require_svg_bank "NEJE_PLOTTER_PLACEHOLDER_ROOT" "Point this to the folder with idle SVG symbols."
launcher_ensure_dir_var "NEJE_PLOTTER_SPOOL_ROOT" "Point this to a writable spool folder."

echo "Idle symbols: $NEJE_PLOTTER_PLACEHOLDER_ROOT"
echo "Layout:       ${NEJE_PLOTTER_LAYOUT_MODE:-hex}"
echo "Spool:        $NEJE_PLOTTER_SPOOL_ROOT"
echo "Operator UI:  http://${NEJE_PLOTTER_OPERATOR_HOST:-0.0.0.0}:${NEJE_PLOTTER_OPERATOR_PORT:-8765}/"
echo

launcher_run_service "neje-plotter"
