#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/scripts/launcher_common.sh" || exit 1

launcher_bootstrap "Thermal Receipt Autoprint" "$SCRIPT_DIR"

if [[ -z "${NEJE_THERMAL_ESP32_URL:-}" ]]; then
  export NEJE_THERMAL_ESP32_URL="http://10.28.8.56"
fi
if [[ -z "${NEJE_THERMAL_CACHE_ROOT:-}" ]]; then
  export NEJE_THERMAL_CACHE_ROOT="$SCRIPT_DIR/runtime/thermal_sessions"
fi

launcher_require_var "NEJE_FIREBASE_PROJECT_ID" "Set it in .env on the MacBook."
launcher_require_var "NEJE_FIREBASE_STORAGE_BUCKET" "Set it in .env on the MacBook."
launcher_require_existing_file_var "NEJE_FIREBASE_CREDENTIALS" "Point this to your Firebase service account JSON."
launcher_ensure_dir_var "NEJE_THERMAL_CACHE_ROOT" "Point this to a writable folder for cached thermal session assets."

echo "ESP32 bridge:  $NEJE_THERMAL_ESP32_URL"
echo "State file:    ${NEJE_THERMAL_STATE_PATH:-$SCRIPT_DIR/runtime/thermal_autoprint.json}"
echo "Cache folder:  $NEJE_THERMAL_CACHE_ROOT"
echo "Firebase poll: latest ${NEJE_THERMAL_FIREBASE_LIMIT:-20} session(s)"
echo

launcher_run_service "neje-thermal-autoprint" "--watch" "--esp32" "$NEJE_THERMAL_ESP32_URL"
