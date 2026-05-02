# public_gallery

Flutter Web public gallery for the Neje Oracle exhibition.

Responsibilities:

- list published sessions from Firestore
- open a stable `#/session/<id>` route from QR codes
- show `publishing` state until Firebase assets are available
- render a mobile digital receipt with SVG mark, oracle text, measured values, themes, and print status

The app does not display visitor photos. Public session data comes from Firestore `sessions/{session_id}` and Firebase Storage files uploaded by the Python uploader.

## Build

Use one static build and deploy it to GitHub Pages from repository root `docs/`:

```bash
../scripts/build_gallery_docs.sh
```

Runtime Firebase settings are loaded from `firebase-config.json` in the deployed web root. The build script creates `docs/firebase-config.json` from `web/firebase-config.example.json` when it does not already exist.

Routes:

- `#/` home
- `#/about` project text
- `#/library` session library
- `#/session/<id>` QR receipt page
