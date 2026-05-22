# Mac Mini Uploader Test Report

Date: 2026-05-18

## File To Use

Give this file to the Mac mini user:

```text
dist/Oracle_MacMini_Uploader_WhatsApp.zip
```

Unzip it and put the whole `Oracle Mac mini Uploader` folder inside the real
TouchDesigner session output folder. Double-click `Oracle Mac mini Uploader.app`.

If you use the private Firebase-key launcher inside the package, it contains the
Firebase key and must not be uploaded to GitHub or shared outside the operator team.

## What It Does

When the Mac mini user double-clicks the file, it:

1. Creates `firebase-service-account.json` beside itself.
2. Creates `macmini_uploader.env`.
3. Creates `.macmini_uploader_runtime/`.
4. Starts the standalone uploader agent on port `8790`.
5. Creates a launch baseline immediately.
6. Starts scanning immediately.
7. Watches the TouchDesigner sessions folder.
8. Uploads new TouchDesigner session folders to Firebase.
9. Downloads the uploaded Firebase QR image back into the session folder.

The user does not need the project source folder.

## Folder Setup

The TouchDesigner output folder should look like this:

```text
TouchDesignerOutput/
  Oracle Mac mini Uploader/
    Oracle Mac mini Uploader.app
    START_ORACLE_UPLOADER.command
    README_MACMINI_UPLOADER.md
  20260518_143000/
    20260518_143000_plotter.svg
    20260518_143000_receipt.txt
    20260518_143000_receipt.csv
    20260518_143000_tarot.jpg
    20260518_143000_tarot_ready.txt
    20260518_143000_qr.png          <- created by uploader after Firebase upload
```

TouchDesigner must create one folder per session.

Each session folder must contain:

```text
<session_id>_plotter.svg
<session_id>_receipt.txt
<session_id>_receipt.csv
<session_id>_tarot.jpg
<session_id>_tarot_ready.txt
```

## Mac Mini User Steps

1. Open the real TouchDesigner output folder.
2. Put the unzipped `Oracle Mac mini Uploader` folder in that folder.
3. Double-click `Oracle Mac mini Uploader.app`.
4. If macOS blocks it, right-click the file, choose Open, then confirm.
5. Leave the Terminal window open.

Good Terminal output:

```text
Standalone Oracle Mac mini Uploader
Sessions folder: <TouchDesigner output folder>
Runtime folder:  <TouchDesigner output folder>/Oracle Mac mini Uploader/.macmini_uploader_runtime
Config file:     <TouchDesigner output folder>/Oracle Mac mini Uploader/macmini_uploader.env
Firebase:        oraclegallery / oraclegallery.firebasestorage.app
Agent:           http://0.0.0.0:8790/
Uploader is scanning for new TouchDesigner sessions now.
```

## NEJE GUI Setup

On the MacBook, set the Mac mini uploader URL:

```bash
NEJE_MACMINI_AGENT_URL=http://<mac-mini-ip>:8790
```

Then in `neje-gui`:

1. Press `NEW RUN`.
2. Press `Find/Scan` in the Mac mini uploader panel.
3. Confirm the Mac mini uploader becomes reachable.
4. Create a new TouchDesigner session after the uploader Terminal says it is scanning.

Important: only sessions created after the uploader launch baseline are uploaded.
Old folders already in the output folder are skipped.

## Upload Result

For each uploaded session, Firebase Storage gets:

```text
sessions/<session_id>/artwork.svg
sessions/<session_id>/artwork_raw.svg
sessions/<session_id>/receipt.txt
sessions/<session_id>/qr.png
sessions/<session_id>/tarot.jpg
sessions/<session_id>/manifest.json
```

The original TouchDesigner session folder gets:

```text
<session_id>_qr.png
```

This QR PNG is downloaded back from Firebase Storage. TouchDesigner can watch for this file and show it on the monitor at the end of the user experience.

Firestore gets:

```text
sessions/<session_id>
plot_jobs/<session_id>
```

Expected Firestore values:

```text
sessions/<session_id>.status = published
sessions/<session_id>.origin = real_macmini
sessions/<session_id>.visibleInLibrary = true
plot_jobs/<session_id>.status = pending
plot_jobs/<session_id>.origin = real_macmini
plot_jobs/<session_id>.visibleInQueue = true
```

## Test Procedure

### 1. Start Uploader

1. Put the command file in the TouchDesigner output folder.
2. Double-click it.
3. Confirm Terminal shows the agent URL.
4. Confirm `firebase-service-account.json` was created beside the command file.

Pass:

```text
Uploader Terminal is open and shows Agent: http://0.0.0.0:8790/
```

### 2. Connect NEJE GUI

1. Start `neje-gui` on the MacBook.
2. Press `NEW RUN`.
3. Press `Find/Scan` in the Mac mini uploader panel.
4. Press `Start` in the Mac mini uploader panel.

Pass:

```text
Mac mini uploader is reachable from neje-gui.
```

### 3. Create One Session

Create one new TouchDesigner session after pressing `Start`.

The new folder must contain:

```text
<session_id>_plotter.svg
<session_id>_receipt.txt
<session_id>_receipt.csv
<session_id>_tarot.jpg
<session_id>_tarot_ready.txt
```

Pass:

```text
The uploader imports the new session within 5-15 seconds.
The session folder receives <session_id>_qr.png.
```

### 4. Check Firebase

Check Firebase Storage:

```text
sessions/<session_id>/artwork.svg
sessions/<session_id>/receipt.txt
sessions/<session_id>/qr.png
sessions/<session_id>/tarot.jpg
```

Check Firestore:

```text
sessions/<session_id>.status = published
plot_jobs/<session_id>.status = pending
```

Pass:

```text
Session exists in Firebase Storage and Firestore.
The local <session_id>_qr.png matches the uploaded Firebase QR asset.
```

### 5. Check Print Queue

In `neje-gui`, confirm the session appears as a pending print job.

Start the dry-run or test print workflow.

Pass:

```text
NEJE GUI downloads the session SVG and creates local plot output.
```

### 6. Check Flutter Web

Open:

```text
https://berlogabob.github.io/OracleGallery/
```

Open the direct session route:

```text
https://berlogabob.github.io/OracleGallery/#/session/<session_id>
```

Pass:

```text
The session appears in the public library and the receipt page opens.
```

## Network Rule

Firebase upload works from any Wi-Fi with internet.

Flutter web works from any Wi-Fi with internet.

NEJE GUI control of the Mac mini uploader needs direct access to:

```text
http://<mac-mini-ip>:8790
```

Use the same Wi-Fi/LAN for the clean test.

## Troubleshooting

If no upload happens, check:

```text
Terminal window is still open.
NEJE GUI pressed Start after NEW RUN.
Session folder was created after Start.
Session folder has <session_id>_plotter.svg.
Session folder has <session_id>_receipt.txt.
Session folder has <session_id>_receipt.csv.
Session folder has <session_id>_tarot.jpg.
Session folder has <session_id>_tarot_ready.txt.
Mac mini has internet.
```

If NEJE GUI cannot connect:

```text
MacBook and Mac mini are on the same Wi-Fi/LAN.
Press Find/Scan in the Mac mini uploader panel.
Port 8790 is not blocked.
```

## Local Verification

Checked locally:

```bash
zsh -n assets/sessions/START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command
python3 -m py_compile <embedded standalone uploader>
```

Result:

```text
Command syntax OK.
Embedded uploader syntax OK.
```
