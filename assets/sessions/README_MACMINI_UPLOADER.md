# Oracle Mac mini Uploader

Use this on the Mac mini that runs TouchDesigner.

## What Goes In The Pack

- `START_ORACLE_UPLOADER.command`: double-click uploader.
- `Oracle Mac mini Uploader.app`: double-click wrapper for macOS.
- `README_MACMINI_UPLOADER.md`: this file.

The private operator pack may also include a launcher that creates `firebase-service-account.json` automatically. If the Firebase key is not embedded, the uploader asks you to drag the Firebase service account JSON into Terminal on first launch.

## Where To Put It

Put the uploader in the real TouchDesigner sessions folder, next to the session folders that TouchDesigner creates.

Example:

```text
TouchDesignerSessions/
  START_ORACLE_UPLOADER.command
  README_MACMINI_UPLOADER.md
  20260522_153000/
    20260522_153000_plotter.svg
    20260522_153000_receipt.txt
    20260522_153000_receipt.csv
    20260522_153000_tarot.jpg
    20260522_153000_tarot_ready.txt
```

If you receive the ZIP package as a folder named `Oracle Mac mini Uploader`, put that folder inside the TouchDesigner sessions folder and double-click the app inside it. The app watches the parent TouchDesigner sessions folder.

## Run

1. Double-click `Oracle Mac mini Uploader.app` or `START_ORACLE_UPLOADER.command`.
2. If macOS blocks it, right-click it once, choose Open, then confirm.
3. Leave the Terminal window open.

On launch, the uploader creates:

```text
firebase-service-account.json
macmini_uploader.env
.macmini_uploader_runtime/
```

## Baseline

The uploader sets a launch baseline every time it starts scanning. Session folders older than that baseline are skipped, so existing folders do not enter the print queue.

Create new TouchDesigner sessions only after the uploader window says it is scanning.

## Session Files

Each new session folder must contain:

```text
<session_id>_plotter.svg
<session_id>_receipt.txt
```

Recommended:

```text
<session_id>_receipt.csv
<session_id>_tarot.jpg
<session_id>_tarot_ready.txt
```

The uploader ignores private visitor files such as `*_visitor.png` and audio files.

## Result

For each new session, the uploader:

1. Creates a public QR code for the gallery receipt page.
2. Uploads SVG, receipt, QR, optional tarot image, and manifest to Firebase.
3. Creates Firestore `sessions/<session_id>` and `plot_jobs/<session_id>`.
4. Downloads the Firebase QR PNG back into the session folder as:

```text
<session_id>_qr.png
```
