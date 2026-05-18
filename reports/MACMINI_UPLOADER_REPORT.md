# Mac Mini Uploader Test Report

Date: 2026-05-18

## File To Use

Give this file to the Mac mini user:

```text
START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command
```

Put it directly inside the real TouchDesigner session output folder.

This is a private file. It contains the Firebase key and must not be uploaded to GitHub or shared outside the operator team.

## What It Does

When the Mac mini user double-clicks the file, it:

1. Creates `firebase-service-account.json` beside itself.
2. Creates `macmini_uploader.env`.
3. Creates `.macmini_uploader_runtime/`.
4. Starts the standalone uploader agent on port `8790`.
5. Watches the same folder where the command file is located.
6. Uploads new TouchDesigner session folders to Firebase.

The user does not need the project source folder.

## Folder Setup

The TouchDesigner output folder should look like this:

```text
TouchDesignerOutput/
  START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command
  20260518_143000/
    20260518_143000_plotter.svg
    20260518_143000_receipt.txt
    READY
```

TouchDesigner must create one folder per session.

Each session folder must contain:

```text
<session_id>_plotter.svg
<session_id>_receipt.txt
READY
```

## Mac Mini User Steps

1. Open the real TouchDesigner output folder.
2. Put `START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command` in that folder.
3. Double-click `START_ORACLE_UPLOADER_WITH_FIREBASE_KEY.command`.
4. If macOS blocks it, right-click the file, choose Open, then confirm.
5. Leave the Terminal window open.

Good Terminal output:

```text
Standalone Oracle Mac mini Uploader
Sessions folder: <TouchDesigner output folder>
Runtime folder:  <TouchDesigner output folder>/.macmini_uploader_runtime
Config file:     <TouchDesigner output folder>/macmini_uploader.env
Firebase:        oraclegallery / oraclegallery.firebasestorage.app
Agent:           http://0.0.0.0:8790/
```

## NEJE GUI Setup

On the MacBook, set the Mac mini uploader URL:

```bash
NEJE_MACMINI_AGENT_URL=http://<mac-mini-ip>:8790
```

Then in `neje-gui`:

1. Press `NEW RUN`.
2. Press `Start` in the Mac mini uploader panel.
3. Create a new TouchDesigner session after pressing `Start`.

Important: only sessions created after `Start` are uploaded. Old folders already in the output folder are skipped.

## Upload Result

For each uploaded session, Firebase Storage gets:

```text
sessions/<session_id>/artwork.svg
sessions/<session_id>/artwork_raw.svg
sessions/<session_id>/receipt.txt
sessions/<session_id>/qr.png
sessions/<session_id>/manifest.json
```

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
2. Confirm `NEJE_MACMINI_AGENT_URL` points to the Mac mini IP.
3. Press `NEW RUN`.
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
READY
```

Pass:

```text
The uploader imports the new session within 5-15 seconds.
```

### 4. Check Firebase

Check Firebase Storage:

```text
sessions/<session_id>/artwork.svg
sessions/<session_id>/receipt.txt
sessions/<session_id>/qr.png
```

Check Firestore:

```text
sessions/<session_id>.status = published
plot_jobs/<session_id>.status = pending
```

Pass:

```text
Session exists in Firebase Storage and Firestore.
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
Session folder has READY.
Mac mini has internet.
```

If NEJE GUI cannot connect:

```text
MacBook and Mac mini are on the same Wi-Fi/LAN.
NEJE_MACMINI_AGENT_URL uses the Mac mini IP.
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
