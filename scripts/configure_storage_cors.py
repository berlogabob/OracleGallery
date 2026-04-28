from __future__ import annotations

import json
from pathlib import Path

from neje_oracle.config import FirebaseSettings
from neje_oracle.firebase_io import FirebaseRemoteRepository


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cors_path = repo_root / "firebase" / "storage.cors.json"
    cors_rules = json.loads(cors_path.read_text(encoding="utf-8"))

    remote = FirebaseRemoteRepository(FirebaseSettings())
    bucket = remote._bucket
    bucket.cors = cors_rules
    bucket.patch()
    print(f"Updated CORS for gs://{bucket.name}")


if __name__ == "__main__":
    main()
