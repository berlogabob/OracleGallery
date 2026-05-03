#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Oracle Operator GUI" "$SCRIPT_DIR"

if [[ -z "${NEJE_UPLOADER_SESSION_ROOT:-}" ]]; then
  export NEJE_UPLOADER_SESSION_ROOT="$SCRIPT_DIR/assets/sessions"
fi
if [[ -z "${NEJE_PLOTTER_SPOOL_ROOT:-}" ]]; then
  export NEJE_PLOTTER_SPOOL_ROOT="$SCRIPT_DIR/spool"
fi

launcher_ensure_dir_var "NEJE_UPLOADER_SESSION_ROOT" "Point this to the TouchDesigner sessions folder."
launcher_ensure_dir_var "NEJE_PLOTTER_SPOOL_ROOT" "Point this to a writable spool folder."

echo "GUI:             http://${NEJE_GUI_HOST:-127.0.0.1}:${NEJE_GUI_PORT:-8787}/"
echo "Sessions folder: $NEJE_UPLOADER_SESSION_ROOT"
echo "Spool folder:    ${NEJE_PLOTTER_SPOOL_ROOT:-$SCRIPT_DIR/spool}"
echo "Mac mini agent:  ${NEJE_MACMINI_AGENT_URL:-not configured}"
echo

launcher_run_service "neje-gui"
