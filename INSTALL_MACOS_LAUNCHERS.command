#!/bin/zsh

set -e
setopt pipefail

REPO_DIR="${0:A:h}"
LAUNCHER_DIR="$REPO_DIR/macos_launchers"

pause() {
  echo
  read '?Press Enter to close...'
}

make_executable() {
  local path="$1"
  if [[ -e "$path" ]]; then
    /bin/chmod u+x "$path" || true
  fi
}

clear_quarantine() {
  local path="$1"
  if [[ -e "$path" ]]; then
    /usr/bin/xattr -dr com.apple.quarantine "$path" >/dev/null 2>&1 || true
  fi
}

write_terminal_app() {
  local app_name="$1"
  local command_path="$2"
  local bundle_id="$3"
  local app_dir="$LAUNCHER_DIR/$app_name.app"
  local launcher="$app_dir/Contents/MacOS/launcher"

  rm -rf "$app_dir"
  mkdir -p "$app_dir/Contents/MacOS"

  cat > "$app_dir/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>$app_name</string>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleIdentifier</key>
  <string>$bundle_id</string>
  <key>CFBundleName</key>
  <string>$app_name</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
</dict>
</plist>
EOF

  cat > "$launcher" <<EOF
#!/bin/zsh

COMMAND_PATH="$command_path"

if [[ ! -f "\$COMMAND_PATH" ]]; then
  /usr/bin/osascript -e 'display alert "Oracle launcher missing" message "Could not find: '"\$COMMAND_PATH"'"'
  exit 1
fi

/bin/chmod u+x "\$COMMAND_PATH" >/dev/null 2>&1 || true
/usr/bin/xattr -d com.apple.quarantine "\$COMMAND_PATH" >/dev/null 2>&1 || true
/usr/bin/open -a Terminal "\$COMMAND_PATH"
EOF

  /bin/chmod +x "$launcher"
  clear_quarantine "$app_dir"
  /usr/bin/codesign --force --deep --sign - "$app_dir" >/dev/null 2>&1 || true
}

cd "$REPO_DIR"

echo "Fixing Oracle macOS launchers..."
echo "Project: $REPO_DIR"
echo

make_executable "$REPO_DIR/start_oracle_gui.command"
make_executable "$REPO_DIR/start_oracle_gui.sh"
make_executable "$REPO_DIR/start_uploader_agent.command"
make_executable "$REPO_DIR/start_uploader_agent.sh"
make_executable "$REPO_DIR/start_plotter_daemon.command"
make_executable "$REPO_DIR/start_plotter_daemon.sh"
make_executable "$REPO_DIR/scripts/launcher_common.sh"
make_executable "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER.command"
make_executable "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command"
make_executable "$REPO_DIR/INSTALL_MACOS_LAUNCHERS.command"

clear_quarantine "$REPO_DIR/start_oracle_gui.command"
clear_quarantine "$REPO_DIR/start_uploader_agent.command"
clear_quarantine "$REPO_DIR/start_plotter_daemon.command"
clear_quarantine "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER.command"
clear_quarantine "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command"

mkdir -p "$LAUNCHER_DIR"
write_terminal_app "Oracle Operator GUI" "$REPO_DIR/start_oracle_gui.command" "gallery.oracle.operator-gui"
write_terminal_app "Oracle Uploader Agent" "$REPO_DIR/start_uploader_agent.command" "gallery.oracle.uploader-agent"
write_terminal_app "Oracle Plotter Daemon" "$REPO_DIR/start_plotter_daemon.command" "gallery.oracle.plotter-daemon"
write_terminal_app "Oracle Mac mini Uploader" "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER.command" "gallery.oracle.macmini-uploader"
write_terminal_app "Oracle Mac mini Uploader Firebase Key" "$REPO_DIR/assets/sessions/START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command" "gallery.oracle.macmini-uploader-key"

clear_quarantine "$LAUNCHER_DIR"

echo "Done."
echo
echo "Double-click apps are in:"
echo "$LAUNCHER_DIR"
echo
echo "Recommended Mac mini app:"
echo "$LAUNCHER_DIR/Oracle Mac mini Uploader.app"
echo
echo "If Finder still warns, right-click the app once and choose Open."
pause
