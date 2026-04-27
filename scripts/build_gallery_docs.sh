#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
GALLERY_DIR="$REPO_DIR/public_gallery"
DOCS_DIR="$REPO_DIR/docs"
BASE_HREF="/OracleGallery/"

cd "$GALLERY_DIR"
flutter pub get
flutter build web --release --base-href "$BASE_HREF" -o "$DOCS_DIR"

touch "$DOCS_DIR/.nojekyll"

if [[ ! -f "$DOCS_DIR/firebase-config.json" ]]; then
  cp "$GALLERY_DIR/web/firebase-config.example.json" "$DOCS_DIR/firebase-config.json"
fi

echo "Gallery built into $DOCS_DIR"
echo "Check docs/firebase-config.json before publishing."
