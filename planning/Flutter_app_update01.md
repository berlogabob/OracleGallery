# План обновления Flutter App и QR/Firebase цепочки

## Summary

QR должен вести на персональную страницу сессии `/#/session/<id>`. Эта страница становится главным QR landing screen: показывает receipt, SVG, текст Oracle, measurements, themes, print status и ссылку `View in the cloth` на библиотеку/ткань с подсветкой этой сессии.

QR PNG должен загружаться в Firebase Storage для дальнейшего использования. В Firestore нужно развести два разных понятия: URL страницы сессии и URL картинки QR. Сейчас они частично смешаны через поле `qrUrl`.

## QR + Firebase Contract

- Генерация QR:
  - `sessionUrl = <NEJE_GALLERY_BASE_URL>/#/session/<encoded_session_id>`
  - QR PNG кодирует строго `sessionUrl`.
  - QR файл сохраняется локально как `sessions_public/<session_id>/qr.png`.
  - QR файл загружается в Firebase Storage как `sessions/<session_id>/qr.png`.

- Firestore `sessions/{session_id}` должен хранить:
  - `sessionId`
  - `sessionUrl`: deep link на `/#/session/<id>`.
  - `qrUrl`: backward-compatible alias на `sessionUrl`, чтобы старый Flutter код не сломался.
  - `qrImageUrl`: public Storage URL картинки `qr.png`.
  - `assetUrls.qr`: тот же `qrImageUrl`.
  - `assetPaths.qr`: `sessions/<session_id>/qr.png`.
  - `svgUrl`, `receiptUrl`, `status`, `plotStatus`, `markName`, `oracleText`, `themes`, `measures`.
  - `origin`, `tags`, `visibleInLibrary`.

- Manifest `manifest.json` должен хранить оба URL:
  - `sessionUrl`
  - `qrImageUrl`
  - `assetPaths.qr`

- Firebase Storage rules остаются public read только под:
  - `sessions/{sessionId}/{fileName}`
  - write from clients disabled.

## Flutter Routing and UX

- QR route остаётся стабильным:
  - `/#/session/<session_id>`
- `/session/:sessionId`:
  - читает `sessions/{session_id}`;
  - если document отсутствует, показывает `publishing`, не 404;
  - если `status != published`, показывает `publishing`;
  - если published, показывает digital receipt;
  - добавляет кнопку/ссылку `View in the cloth`, ведущую на `/#/cloth?session=<session_id>`.
- `/cloth`:
  - заменяет смысл старой `/library`;
  - показывает public library/cloth из Firestore;
  - принимает query `session=<id>`;
  - подсвечивает найденный mark;
  - скрывает sessions с `visibleInLibrary=false`, `origin=test`, `tags` containing `test`.
- `/library`:
  - оставить как redirect/alias на `/cloth`, чтобы старые ссылки не сломались.
- Navigation:
  - `Home`
  - `The Cloth`
  - `The Marks`
  - `About`
- `SessionData` модель во Flutter должна читать:
  - `sessionUrl`
  - `qrUrl`
  - `qrImageUrl`
  - fallback `assetUrls.qr`
  - текущие поля `svgUrl`, `receiptUrl`.

## Flutter Design Update

- Разделить `public_gallery/lib/main.dart` на небольшие модули:
  - `app.dart`
  - `theme/oracle_theme.dart`
  - `models/session_data.dart`
  - `services/session_repository.dart`
  - `widgets/oracle_shell.dart`
  - `widgets/oracle_primitives.dart`
  - `pages/home_page.dart`
  - `pages/cloth_page.dart`
  - `pages/marks_page.dart`
  - `pages/about_page.dart`
  - `pages/session_receipt_page.dart`

- Визуальная система:
  - cream document background;
  - void sections for mark/hero areas;
  - gold/rust accents;
  - thin rules;
  - `Cinzel`, `Cinzel Decorative`, `EB Garamond`;
  - no visitor photo/audio/transcript.
- Home:
  - atmospheric Oracle intro;
  - session lookup input;
  - links to cloth/marks/about.
- The Cloth:
  - live Firestore mark register;
  - count of visible marks;
  - session lookup and highlighted mark.
- The Marks:
  - 8 base marks from `assets/symbols`;
  - static descriptions from narrative/wireframe.
- About:
  - project context;
  - how it works;
  - AI systems;
  - team/video placeholders if final copy/assets are missing.
- Session Receipt:
  - mobile-first receipt layout;
  - mark SVG;
  - oracle text;
  - measurements;
  - themes;
  - print status;
  - QR/session metadata link to cloth.

## Python Uploader Changes

- In `SessionUploader._stage_public_assets`:
  - rename internal generated URL concept to `session_url`;
  - generate `qr.png` from `session_url`;
  - store `record.qr_url = session_url` for compatibility.
- In `FirebaseRemoteRepository.publish_session`:
  - upload `qr.png` to Storage;
  - compute `qr_image_url`;
  - write Firestore:
    - `sessionUrl = record.qr_url`
    - `qrUrl = record.qr_url`
    - `qrImageUrl = qr_image_url`
    - `assetUrls.qr = qr_image_url`
    - `assetPaths.qr = sessions/<id>/qr.png`
- In local store/manifest:
  - keep existing columns;
  - add manifest fields for `sessionUrl` and `qrImageUrl` if not already present through public fields.

## Test Plan

- Python uploader:
  - generated `qr.png` exists for a staged session;
  - stored `record.qr_url` equals `<gallery_base>/#/session/<id>`;
  - Firestore payload includes `sessionUrl`, `qrUrl`, `qrImageUrl`, `assetUrls.qr`, `assetPaths.qr`;
  - QR PNG upload path is `sessions/<id>/qr.png`;
  - visitor image/audio/transcript are still ignored.

- Flutter:
  - `/#/session/<id>` loads document by session id;
  - missing session shows `publishing`;
  - published session shows receipt;
  - receipt page links to `/#/cloth?session=<id>`;
  - `/library` redirects or aliases to `/cloth`;
  - `/cloth?session=<id>` highlights session;
  - test sessions are hidden from cloth/library.
  - Firebase config missing shows graceful config state.

- Build:
  - `cd public_gallery && flutter analyze`
  - `./scripts/build_gallery_docs.sh`
  - manually open:
    - `/#/`
    - `/#/cloth`
    - `/#/library`
    - `/#/marks`
    - `/#/about`
    - `/#/session/test_id`

## Acceptance Criteria

- QR from receipt opens the user’s personal session page.
- QR PNG is uploaded to Firebase Storage and recoverable through Firestore.
- Firestore no longer ambiguously uses `qrUrl` as both image URL and deep link.
- Public library/cloth does not show test sessions.
- Session page can lead user into the library/cloth view for their mark.
- Existing QR route compatibility is preserved.
- Flutter app matches the Oracle wireframe direction without changing Python plotter behavior.

## Assumptions

- Chosen QR target: `/#/session/<id>`.
- `qrUrl` remains a backward-compatible deep link.
- New image field is `qrImageUrl`.
- `/cloth` is the new public library page.
- `/library` stays as compatibility alias.
- Flutter remains read-only against Firebase.
- Python plotter/FluidNC pipeline is out of scope for this design pass.
