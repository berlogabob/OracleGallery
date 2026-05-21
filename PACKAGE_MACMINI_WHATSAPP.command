#!/bin/zsh

set -e
setopt pipefail

REPO_DIR="${0:A:h}"
BUILD_ROOT="$REPO_DIR/dist/macmini_whatsapp"
PACKAGE_DIR="$BUILD_ROOT/Oracle Mac mini Uploader"
APP_DIR="$PACKAGE_DIR/Oracle Mac mini Uploader.app"
DEFAULT_COMMAND_NAME="START_ORACLE_UPLOADER.command"
PRIVATE_COMMAND_NAME="START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command"
if [[ -n "${ORACLE_MACMINI_COMMAND_NAME:-}" ]]; then
  COMMAND_NAME="$ORACLE_MACMINI_COMMAND_NAME"
elif [[ -f "$REPO_DIR/assets/sessions/$PRIVATE_COMMAND_NAME" ]]; then
  COMMAND_NAME="$PRIVATE_COMMAND_NAME"
else
  COMMAND_NAME="$DEFAULT_COMMAND_NAME"
fi
SOURCE_COMMAND="$REPO_DIR/assets/sessions/$COMMAND_NAME"
ZIP_PATH="$REPO_DIR/dist/Oracle_MacMini_Uploader_WhatsApp.zip"

pause() {
  echo
  read '?Press Enter to close...'
}

fail() {
  echo
  echo "ERROR: $1"
  pause
  exit 1
}

[[ -f "$SOURCE_COMMAND" ]] || fail "Missing launcher command: $SOURCE_COMMAND"

/bin/rm -rf "$BUILD_ROOT"
/bin/mkdir -p "$PACKAGE_DIR" "$APP_DIR/Contents/MacOS"

/bin/cp "$SOURCE_COMMAND" "$PACKAGE_DIR/START_ORACLE_UPLOADER.command"

/bin/chmod u+x "$PACKAGE_DIR/START_ORACLE_UPLOADER.command"
/usr/bin/xattr -dr com.apple.quarantine "$PACKAGE_DIR" >/dev/null 2>&1 || true

cat > "$APP_DIR/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Oracle Mac mini Uploader</string>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleIdentifier</key>
  <string>gallery.oracle.macmini.whatsapp.uploader</string>
  <key>CFBundleName</key>
  <string>Oracle Mac mini Uploader</string>
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

cat > "$APP_DIR/Contents/MacOS/launcher" <<'EOF'
#!/bin/zsh

APP_DIR="${0:A:h:h:h}"
PACKAGE_DIR="${APP_DIR:h}"
COMMAND_PATH="$PACKAGE_DIR/START_ORACLE_UPLOADER.command"

if [[ ! -f "$COMMAND_PATH" ]]; then
  /usr/bin/osascript -e 'display alert "Oracle uploader missing" message "START_ORACLE_UPLOADER.command must stay next to this app."'
  exit 1
fi

/bin/chmod u+x "$COMMAND_PATH" >/dev/null 2>&1 || true
/usr/bin/xattr -d com.apple.quarantine "$COMMAND_PATH" >/dev/null 2>&1 || true
/usr/bin/osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "zsh " & quoted form of "$COMMAND_PATH"
end tell
APPLESCRIPT
EOF

/bin/chmod +x "$APP_DIR/Contents/MacOS/launcher"
/usr/bin/codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true

cat > "$PACKAGE_DIR/OPEN_ME_FIRST.txt" <<'EOF'
ORACLE MAC MINI UPLOADER

1. Double-click: Oracle Mac mini Uploader.app
2. If macOS Tahoe blocks the app, run START_ORACLE_UPLOADER.command directly.
3. Keep this app in the same folder as START_ORACLE_UPLOADER.command.
4. Put TouchDesigner session folders in this same folder.

If macOS blocks the first launch:
- Right-click Oracle Mac mini Uploader.app
- Click Open
- Click Open again

After that, normal double-click should work.

This package creates its Firebase JSON and uploader config inside this folder on first launch.
EOF

/usr/bin/xattr -dr com.apple.quarantine "$PACKAGE_DIR" >/dev/null 2>&1 || true
/bin/mkdir -p "$REPO_DIR/dist"
/bin/rm -f "$ZIP_PATH"
(
  cd "$BUILD_ROOT"
  COPYFILE_DISABLE=1 /usr/bin/zip -qry -X "$ZIP_PATH" "Oracle Mac mini Uploader"
)

echo "Created WhatsApp-ready ZIP:"
echo "$ZIP_PATH"
echo
echo "Send this ZIP file, not the raw .command file."
echo "She should unzip it and double-click Oracle Mac mini Uploader.app."
pause
