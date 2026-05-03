#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Oracle Mac mini Uploader Agent" "$SCRIPT_DIR"

launcher_require_var "NEJE_FIREBASE_PROJECT_ID" "Set it in .env on the Oracle Mac mini."
launcher_require_var "NEJE_FIREBASE_STORAGE_BUCKET" "Set it in .env on the Oracle Mac mini."
launcher_require_existing_file_var "NEJE_FIREBASE_CREDENTIALS" "Point this to your Firebase service account JSON."
launcher_require_existing_dir_var "NEJE_UPLOADER_SESSION_ROOT" "Point this to the TouchDesigner sessions folder."
launcher_ensure_dir_var "NEJE_UPLOADER_PUBLIC_ROOT" "Point this to a writable folder for published session assets."

echo "Agent:     http://${NEJE_UPLOADER_AGENT_HOST:-0.0.0.0}:${NEJE_UPLOADER_AGENT_PORT:-8790}/"
echo "Watching:  $NEJE_UPLOADER_SESSION_ROOT"
echo "Publishing: $NEJE_UPLOADER_PUBLIC_ROOT"
echo

launcher_run_service "neje-uploader-agent"
