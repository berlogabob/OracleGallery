# macOS Launchers

## WhatsApp Transfer

Do not send raw `.command` files through WhatsApp. Send a ZIP package instead:

```sh
zsh PACKAGE_MACMINI_WHATSAPP.command
```

This creates:

```text
dist/Oracle_MacMini_Uploader_WhatsApp.zip
```

Send that ZIP to the Mac mini user. She should unzip it, put the whole
`Oracle Mac mini Uploader` folder inside the real TouchDesigner sessions folder,
and double-click:

```text
Oracle Mac mini Uploader/Oracle Mac mini Uploader.app
```

The app watches the parent TouchDesigner sessions folder. Existing session folders
are skipped by the launch baseline; only new sessions created after the uploader
starts scanning are uploaded and added to the print queue.

If macOS blocks the first launch, right-click the app and choose **Open** once.

## Local Repo Launchers

If macOS refuses to run an Oracle `.command` file by double-click, run:

```sh
zsh INSTALL_MACOS_LAUNCHERS.command
```

The installer fixes executable permissions, removes quarantine attributes from the Oracle launchers, and creates local double-click `.app` wrappers in `macos_launchers/`.

For the Mac mini, use:

```text
macos_launchers/Oracle Mac mini Uploader.app
```

If Finder still shows a security warning the first time, right-click the app and choose **Open** once. After that, normal double-click should work.
