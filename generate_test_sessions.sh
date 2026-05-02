#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Oracle Test Session Generator" "$SCRIPT_DIR"

if [[ -z "${NEJE_UPLOADER_SESSION_ROOT:-}" ]]; then
  export NEJE_UPLOADER_SESSION_ROOT="$SCRIPT_DIR/assets/sessions"
fi

if [[ $# -gt 0 ]]; then
  launcher_run_service "neje-generate-sessions" "$@"
fi

echo "Generating one test user session."
echo "Output folder: $NEJE_UPLOADER_SESSION_ROOT"
echo "If the uploader is running, this session will be published to Firebase and queued for printing."
echo

launcher_run_service "neje-generate-sessions" --mode user --count "${NEJE_GENERATOR_COUNT:-1}" --output-root "$NEJE_UPLOADER_SESSION_ROOT"
