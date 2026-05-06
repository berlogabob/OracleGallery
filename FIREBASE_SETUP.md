# Oracle Firebase Setup

Firebase is used for public receipt data, public SVG/TXT/QR assets, and real user plot jobs. It is not used to control idle/filler printing and the Flutter app is read-only.

## Project

```text
Project ID: oraclegallery
Storage bucket: oraclegallery.firebasestorage.app
Gallery URL: https://berlogabob.github.io/OracleGallery
QR route: https://berlogabob.github.io/OracleGallery/#/session/<session_id>
```

Enable:

- Cloud Firestore.
- Firebase Storage.

Not required for v1:

- Firebase Auth.
- Cloud Messaging.
- Flutter client writes.

## Python Admin Credentials

Download the Firebase service account JSON and keep it outside git, for example:

```text
/Users/berloga/.oracle/secrets/oraclegallery-firebase-adminsdk.json
```

Set the Python service environment:

```bash
NEJE_FIREBASE_PROJECT_ID=oraclegallery
NEJE_FIREBASE_STORAGE_BUCKET=oraclegallery.firebasestorage.app
NEJE_FIREBASE_CREDENTIALS=/Users/berloga/.oracle/secrets/oraclegallery-firebase-adminsdk.json
NEJE_GALLERY_BASE_URL=https://berlogabob.github.io/OracleGallery
```

The uploader and plotter queue worker use the Admin SDK with this service account. Do not put the service account file in `public_gallery`, `docs`, or any committed folder.

## Flutter Web Config

The public web config lives in:

```text
public_gallery/lib/firebase_config.dart
```

Current web app values:

```dart
const FirebaseOptions(
  apiKey: 'AIzaSyDqBzqcDefYypWiu6vC15WVQVlisgMypIg',
  authDomain: 'oraclegallery.firebaseapp.com',
  projectId: 'oraclegallery',
  storageBucket: 'oraclegallery.firebasestorage.app',
  messagingSenderId: '690305000229',
  appId: '1:690305000229:web:63d9d74d5030dbaefcf0cc',
  measurementId: 'G-2FXB448E74',
)
```

This key is public Firebase web config, not an Admin credential. Public gallery writes remain disabled by rules and by application code.

## Firestore Contract

Public session document:

```text
sessions/{session_id}
```

Required public fields:

```text
sessionId
createdAt
status
plotStatus
markName
oracleText
themes
measures
svgUrl
receiptUrl
sessionUrl
qrUrl
qrImageUrl
assetUrls.svg
assetUrls.receipt
assetUrls.qr
assetPaths.svg
assetPaths.receipt
assetPaths.qr
origin
tags
visibleInLibrary
```

`sessionUrl` and `qrUrl` are page links. `qrImageUrl` and `assetUrls.qr` are PNG Storage URLs. Session documents are public-readable because direct QR links must show a publishing state instead of a permission error; no private photos, audio, or transcripts may be written to these documents.

Print job document:

```text
plot_jobs/{session_id}
```

Important fields:

```text
sessionId
createdAt
status
priority
queue
svgStoragePath
svgUrl
origin
tags
visibleInQueue
```

Test sessions:

```text
origin=test
tags=["test", "generated"]
visibleInLibrary=false
```

Real sessions:

```text
origin=oracle
tags=["real"]
visibleInLibrary=true
```

## Rules

Firestore v1 rules:

```javascript
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    match /sessions/{sessionId} {
      allow read: if true;
      allow write: if false;
    }

    match /plot_jobs/{jobId} {
      allow read, write: if false;
    }

    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Storage v1 rules:

```javascript
rules_version = '2';

service firebase.storage {
  match /b/{bucket}/o {
    match /sessions/{sessionId}/{fileName} {
      allow read: if true;
      allow write: if false;
    }

    match /{allPaths=**} {
      allow read, write: if false;
    }
  }
}
```

Deploy rules from the repository root:

```bash
npx firebase-tools deploy --project oraclegallery --config firebase/firebase.json --only firestore:rules,firestore:indexes,storage
```

If deployment fails with `serviceusage.services.use`, log in to the Firebase CLI with the Google account that owns the project or grant that account Service Usage Consumer/Owner on the Google Cloud project.

## Verification

Run:

```bash
uv run pytest
cd public_gallery && flutter analyze
```

Manual checks:

- Upload one session folder with SVG/TXT/READY.
- Confirm Storage has `artwork.svg`, `artwork_raw.svg`, `receipt.txt`, `qr.png`, `manifest.json`.
- Confirm no visitor PNG/audio/transcript is uploaded.
- Confirm Firestore `sessions/{id}.sessionUrl` opens `/#/session/<id>`.
- Confirm Firestore `sessions/{id}.qrImageUrl` opens the PNG.
- Confirm `plot_jobs/{id}` exists for a real user session.
