#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Oracle Firebase Uploader" "$SCRIPT_DIR"

launcher_require_var "NEJE_FIREBASE_PROJECT_ID" "Set it in .env on the Oracle Mac mini."
launcher_require_var "NEJE_FIREBASE_STORAGE_BUCKET" "Set it in .env on the Oracle Mac mini."
launcher_require_existing_file_var "NEJE_FIREBASE_CREDENTIALS" "Point this to your Firebase service account JSON."
launcher_require_var "NEJE_GALLERY_BASE_URL" "Set the public GitHub Pages URL in .env."
launcher_require_existing_dir_var "NEJE_UPLOADER_SESSION_ROOT" "Point this to the TouchDesigner sessions folder."
launcher_ensure_dir_var "NEJE_UPLOADER_PUBLIC_ROOT" "Point this to a writable folder for published session assets."

echo "Watching:  $NEJE_UPLOADER_SESSION_ROOT"
echo "Publishing: $NEJE_UPLOADER_PUBLIC_ROOT"
echo "Gallery:   $NEJE_GALLERY_BASE_URL"
echo

launcher_run_service "neje-uploader"

