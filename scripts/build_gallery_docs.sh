#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
GALLERY_DIR="$REPO_DIR/public_gallery"
DOCS_DIR="$REPO_DIR/docs"
BASE_HREF="/OracleGallery/"
CONFIG_BACKUP=""

if [[ -f "$DOCS_DIR/firebase-config.json" ]]; then
  CONFIG_BACKUP="$(mktemp)"
  cp "$DOCS_DIR/firebase-config.json" "$CONFIG_BACKUP"
fi

rm -rf "$DOCS_DIR"

cd "$GALLERY_DIR"
flutter pub get
flutter build web --release --base-href "$BASE_HREF" -o "$DOCS_DIR"

touch "$DOCS_DIR/.nojekyll"

if [[ -n "$CONFIG_BACKUP" && -f "$CONFIG_BACKUP" ]]; then
  cp "$CONFIG_BACKUP" "$DOCS_DIR/firebase-config.json"
  rm -f "$CONFIG_BACKUP"
elif [[ ! -f "$DOCS_DIR/firebase-config.json" ]]; then
  cp "$GALLERY_DIR/web/firebase-config.example.json" "$DOCS_DIR/firebase-config.json"
fi

echo "Gallery built into $DOCS_DIR"
echo "Check docs/firebase-config.json before publishing."
