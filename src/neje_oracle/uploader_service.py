from __future__ import annotations

import time

from .config import FirebaseSettings, UploaderSettings
from .firebase_io import FirebaseRemoteRepository
from .session_uploader import SessionUploader
from .store import UploaderStore


def main() -> None:
    firebase_settings = FirebaseSettings()
    uploader_settings = UploaderSettings()
    store = UploaderStore(uploader_settings.db_path)
    remote = FirebaseRemoteRepository(firebase_settings)
    uploader = SessionUploader(uploader_settings, firebase_settings, store, remote)
    while True:
        uploader.scan_once()
        time.sleep(uploader_settings.poll_seconds)

