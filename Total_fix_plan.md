# Детальный план восстановления проекта по 5 критичным пунктам

## Current status — 2026-05-06

- ✅ Flutter routing/theme/pages restored to a compiling read-only public gallery.
- ✅ `SessionRepository` is read-only Firestore; Auth/Storage/write paths removed from Flutter.
- ✅ Python Supervisor tests updated to current responsibilities; full `uv run pytest` passes.
- ✅ `README.md`, `FIREBASE_SETUP.md`, and `RUNBOOK.md` restored to Oracle-specific architecture.
- ✅ QR contract implemented: `sessionUrl` / `qrUrl` are receipt links; `qrImageUrl` / `assetUrls.qr` are Storage PNG URLs.
- ✅ GitHub Pages build regenerated into `docs/`.
- ✅ `git diff --check` passes.

## Summary

Цель: вернуть проект в рабочее состояние после последних изменений, затем безопасно продолжить Flutter redesign и QR/Firebase contract. Сначала восстанавливаем компиляцию и тесты, потом приводим публичную Flutter-витрину к read-only архитектуре, затем фиксируем QR поля `sessionUrl` / `qrImageUrl`.

Текущий baseline проверки:
- `uv run python -m py_compile src/neje_oracle/*.py` проходит.
- `uv run pytest` падает: `5 failed, 72 passed`.
- `flutter analyze` падает: `170 issues`.
- `git diff --check` падает из-за trailing whitespace.
- `README.md` и `FIREBASE_SETUP.md` сейчас содержат generic NejeDraw/мобильное приложение, не Oracle architecture.

## 1. Вернуть Flutter к компилируемой базе

### 1.1. Зафиксировать текущие Flutter ошибки

1. Открыть `public_gallery/lib/main.dart`.
2. Открыть `public_gallery/lib/global_router_delegate.dart`.
3. Открыть `public_gallery/lib/models/session_data.dart`.
4. Открыть `public_gallery/lib/services/session_repository.dart`.
5. Сверить ошибки `flutter analyze` с кодом.
6. Разделить ошибки на группы:
   - routing errors;
   - wrong imports;
   - wrong Firebase package usage;
   - invalid Google Fonts;
   - wrong model/repository contract;
   - unused/obsolete files.

### 1.2. Починить imports

1. В `public_gallery/lib/main.dart` заменить неверный import:
   - было: `package:cloud_firestore/firebase_firestore.dart`
   - должно быть: `package:cloud_firestore/cloud_firestore.dart`
2. Добавить правильный import для hash routing:
   - `package:flutter_web_plugins/url_strategy.dart`
3. Удалить неиспользуемые imports:
   - `global_router_delegate.dart`, если отказываемся от custom delegate.
   - `session_repository.dart`, если `main.dart` напрямую его не использует.
4. В `public_gallery/lib/pages/marks_page.dart` добавить import:
   - `package:google_fonts/google_fonts.dart`
   - либо убрать прямой вызов `GoogleFonts` и использовать theme.
5. В `public_gallery/lib/widgets/oracle_primitives.dart` добавить import:
   - `package:google_fonts/google_fonts.dart`
   - либо заменить на theme styles.
6. В `public_gallery/lib/pages/cloth_page.dart` добавить import:
   - `package:flutter_svg/flutter_svg.dart`, если используется `SvgPicture`.

### 1.3. Упростить routing

1. Удалить использование `GlobalRouterDelegate` из `main.dart`.
2. Использовать только `MaterialApp.router`.
3. Создать один `GoRouter` внутри `OracleGalleryApp`.
4. Routes:
   - `/`
   - `/cloth`
   - `/library`
   - `/marks`
   - `/about`
   - `/session/:sessionId`
5. `/library` сделать redirect на `/cloth`.
6. Для `go_router ^15` использовать:
   - `state.pathParameters['sessionId']`
   - не использовать `state.params`.
7. Не использовать named parameter `title` в `GoRoute`, потому что он не поддерживается текущим API.
8. Убедиться, что `HashUrlStrategy` остаётся включённым.
9. Удалить или оставить неиспользуемый `global_router_delegate.dart` только если он не импортируется.
10. Если файл остаётся, он не должен ломать analyze:
   - либо привести его к валидному коду;
   - либо удалить из `lib/`, если не нужен.

### 1.4. Починить MaterialApp

1. Заменить `MaterialApp(...)` с router-полями на `MaterialApp.router(...)`.
2. Передать:
   - `title`
   - `debugShowCheckedModeBanner`
   - `theme`
   - `routerConfig: router`
3. Если нужен shell вокруг всех pages, использовать `ShellRoute` в `GoRouter`.
4. Не использовать `builder: OracleShell(child: child!)`, если `OracleShell` ожидает route context/current path.
5. Проверить, что nav active state берётся из текущего route.

### 1.5. Починить theme

1. Открыть `public_gallery/lib/theme/oracle_theme.dart`.
2. Сделать публичные constants или class:
   - `OracleColors.cream`
   - `OracleColors.paper`
   - `OracleColors.ink`
   - `OracleColors.rust`
   - `OracleColors.gold`
   - `OracleColors.voidColor`
3. Убрать private constants `_cream`, `_paper`, если они не используются.
4. В `main.dart` не ссылаться на `_charcoal`, `_cream`, `_paper`, если они определены в другом файле.
5. Заменить несуществующие:
   - `GoogleFonts.era()`
   - `GoogleFonts.eraTextTheme()`
6. Использовать:
   - `GoogleFonts.ebGaramondTextTheme()`
   - `GoogleFonts.cinzel()`
   - `GoogleFonts.cinzelDecorative()`
7. `ColorScheme` создать через `ColorScheme.fromSeed` или полный constructor со всеми required fields.
8. Убрать deprecated `background/onBackground`, если легко заменить на `surface/onSurface`.
9. Не включать `darkTheme` сейчас, если дизайн-система не требует dark mode. Для Oracle лучше один controlled visual theme.

### 1.6. Проверить Flutter после первого исправления

1. Запустить:
   - `cd public_gallery && flutter analyze`
2. Исправлять только compile-level errors.
3. Warnings типа `unnecessary_const` оставить на потом, если они не мешают.
4. После исчезновения errors перейти к repository/model.

## 2. Упростить SessionRepository до read-only

### 2.1. Определить правильный public contract

1. Flutter public app не должен писать в Firebase.
2. Удалить из `SessionRepository`:
   - auth dependency;
   - storage dependency;
   - create session;
   - update session;
   - delete session;
   - upload file;
   - download file;
   - owner checks;
   - offline mode toggle, если он ломает web.
3. Оставить только:
   - `Stream<SessionData?> watchSession(String sessionId)`
   - `Stream<List<SessionData>> watchVisibleSessions()`
   - `Future<SessionData?> fetchSession(String sessionId)` если нужен lookup one-shot.
4. Firebase access только read-only Firestore.
5. Storage URLs читать из Firestore fields, не использовать Firebase Storage SDK во Flutter.

### 2.2. Починить SessionData

1. Сделать `SessionData` immutable.
2. Поля:
   - `sessionId`
   - `createdAt`
   - `status`
   - `plotStatus`
   - `markName`
   - `oracleText`
   - `themes`
   - `measures`
   - `svgUrl`
   - `receiptUrl`
   - `qrUrl`
   - `sessionUrl`
   - `qrImageUrl`
   - `origin`
   - `tags`
   - `visibleInLibrary`
3. `measures` сделать `Map<String, double>`, потому что Python пишет map.
4. `themes` сделать `List<String>`.
5. `assetUrls` читать как `Map<String, dynamic>`, не cast напрямую в `Map<String, String>`.
6. Factory:
   - `SessionData.fromDoc(DocumentSnapshot<Map<String, dynamic>> doc)`
7. Fallbacks:
   - `sessionId = data['sessionId'] ?? doc.id`
   - `svgUrl = assetUrls['svg'] ?? data['svgUrl'] ?? ''`
   - `receiptUrl = assetUrls['receipt'] ?? data['receiptUrl'] ?? ''`
   - `sessionUrl = data['sessionUrl'] ?? data['qrUrl'] ?? ''`
   - `qrImageUrl = data['qrImageUrl'] ?? assetUrls['qr'] ?? ''`
   - `qrUrl = data['qrUrl'] ?? sessionUrl`
8. Avoid direct `Object[]` access:
   - cast `doc.data()` to `Map<String, dynamic>?`.

### 2.3. Починить visible sessions query

1. Начать с простого query:
   - `collection('sessions')`
   - `where('status', isEqualTo: 'published')`
   - `orderBy('createdAt', descending: true)`
2. Фильтрацию test sessions делать в Dart после snapshot:
   - hide if `visibleInLibrary == false`
   - hide if `origin == 'test'`
   - hide if `tags` contains `test`
3. Причина: Firestore compound filters + `isNotEqualTo` требуют индексы и могут ломать первый запуск.
4. Позже можно добавить индексы, если будет нужна server-side фильтрация.
5. `createdAt` field использовать именно camelCase, потому что Python publisher пишет `createdAt`.

### 2.4. Починить ClothPage

1. `ClothPage` должен принимать optional:
   - `highlightSessionId`
2. Для `/cloth?session=<id>` брать query:
   - `state.uri.queryParameters['session']`
3. `StreamBuilder<List<SessionData>>`, не `DocumentSnapshot`.
4. Не пытаться создавать `QuerySnapshot` вручную.
5. Если stream error:
   - показать `ErrorState`.
6. Если sessions empty:
   - показать `EmptyState`.
7. Если highlight id найден:
   - выделить эту карточку/ячейку.
8. Если highlight id не найден:
   - показать quiet notice `Session is not visible in the cloth yet`.

### 2.5. Починить SessionReceiptPage

1. Использовать `SessionRepository().watchSession(sessionId)`.
2. `StreamBuilder<SessionData?>`.
3. Если `snapshot.connectionState == waiting`:
   - показать loading receipt shell.
4. Если `snapshot.data == null`:
   - показать publishing state.
5. Если `session.status != 'published'`:
   - показать publishing state.
6. Если published:
   - показать receipt.
7. Добавить link:
   - route `/cloth?session=<sessionId>`.
8. Использовать `SvgPicture.network(session.svgUrl)` только если URL не пустой.
9. Если SVG URL пустой:
   - показать mark placeholder.

### 2.6. Удалить mock repository или привести к контракту

1. Если mock нужен для Firebase missing state:
   - `MockSessionRepository` должен реализовать те же read-only methods.
2. Не пытаться создавать `DocumentSnapshot` или `QuerySnapshot` вручную.
3. Лучше для v1 удалить `mock_session_repository.dart`, если не используется.
4. Firebase missing state пусть обрабатывается на уровне pages:
   - `firebaseReady == false` -> config help.

### 2.7. Проверка

1. Запустить:
   - `cd public_gallery && flutter analyze`
2. Исправить все errors.
3. Warnings оставить только если они не мешают build.
4. После analyze без errors запустить:
   - `cd public_gallery && flutter build web --base-href /OracleGallery/`
5. Если build проходит, не запускать deploy.

## 3. Исправить Python tests вокруг SupervisorService

### 3.1. Разобрать новые failing tests

1. Открыть:
   - `tests/test_supervisor_cell_info.py`
   - `tests/test_supervisor_validation.py`
2. Зафиксировать, что они ожидают API:
   - `SupervisorService(settings=..., runtime_store=..., gcode_file=...)`
   - `supervisor.get_current_cell_info()`
   - `supervisor.start_system()` без `PlotterRuntimeConfig`
3. Сравнить с реальным API:
   - `SupervisorService(settings=None, plotter_settings=None, runtime_store=None, remote_factory=None, transport_factory=None)`
   - `start_system(config: PlotterRuntimeConfig)`
   - progress хранится в `PlotterRuntimeState`, а не через standalone `gcode_file`.

### 3.2. Решить стратегию

1. Не добавлять `gcode_file` в `SupervisorService`.
2. Причина: Supervisor не должен парсить произвольный G-code файл; он управляет daemon/runtime/control.
3. Точные cell markers должны жить в:
   - `svg_gcode.py`
   - `transport.py` progress callback
   - `plotter_daemon.py` runtime state
4. Поэтому failing tests нужно переписать под реальные места ответственности.

### 3.3. Переписать `test_supervisor_cell_info.py`

1. Удалить ожидание `SupervisorService(..., gcode_file=...)`.
2. Если нужно тестировать parser markers:
   - вынести parser helper в подходящий модуль, например `svg_gcode.py` или новый `gcode_progress.py`.
3. Тестировать helper напрямую:
   - input gcode with `; cell-start`
   - expect parsed cell sequence.
4. Если parser helper пока не существует:
   - создать планируемый helper в implementation phase.
5. Для текущей проверки runtime:
   - использовать `PlotterDaemon` dry-run test.
   - запустить `daemon.run_cycle()`.
   - проверить `PlotterRuntimeState.current_cell_index`, `current_cell_in_row`, `row_cell_count`.

### 3.4. Переписать `test_supervisor_validation.py`

1. Удалить проверки `start_system` на `gcode_file`.
2. Валидация перед реальной печатью уже покрывается:
   - preflight;
   - readiness;
   - FluidNC state;
   - `start_print`.
3. Переписать tests на:
   - `start_print` blocked without preflight.
   - `start_print` blocked without readiness.
   - `start_print` blocked in real mode without arm.
   - `start_print` blocked if FluidNC not Idle in real mode.
4. Для G-code markers:
   - тестировать `generate_sheet_gcode` marker output.
   - тестировать daemon progress behavior.
5. Не смешивать `start_system` и `start_print`: `start_system` запускает supervised services, а не печать.

### 3.5. Проверка Python

1. Запустить:
   - `uv run pytest tests/test_supervisor_cell_info.py tests/test_supervisor_validation.py`
2. Затем:
   - `uv run pytest`
3. Ожидаемый результат:
   - all tests pass.
4. Если появляются реальные failures в daemon/transport:
   - исправлять production code, не ослаблять safety tests.

## 4. Восстановить Oracle documentation

### 4.1. README

1. Открыть текущий `README.md`.
2. Удалить generic content:
   - APK/IPA downloads;
   - `yourusername/neje-draw`;
   - mobile app quick start;
   - push notifications;
   - multi-language marketing;
   - generic NejeDraw features.
3. Вернуть Oracle architecture sections:
   - Oracle Mac mini uploader;
   - MacBook operator GUI;
   - Firebase/Firestore/Storage;
   - Flutter Gallery on GitHub Pages;
   - Plotter/FluidNC;
   - Session contract;
   - QR route;
   - important env vars;
   - verification commands.
4. Убедиться, что README говорит:
   - Mac mini runs only uploader agent.
   - MacBook runs `neje-gui`.
   - QR route is `https://berlogabob.github.io/OracleGallery/#/session/<id>`.
   - Flutter is read-only.
5. Убрать trailing whitespace.

### 4.2. FIREBASE_SETUP.md

1. Удалить generic Firebase Auth/Push setup.
2. Оставить project-specific setup:
   - project id `oraclegallery`;
   - Firestore enabled;
   - Storage enabled;
   - GitHub Pages config;
   - web config file path;
   - Python Admin credentials path;
   - rules deploy command.
3. Rules section:
   - public read for `sessions`;
   - public read Storage under `sessions/{sessionId}/{fileName}`;
   - client write disabled.
4. Explicitly state:
   - no Firebase Auth required for public gallery v1.
   - no Flutter client writes.
   - Python service account writes uploader/plotter data.
5. Add QR fields:
   - `sessionUrl`
   - `qrUrl`
   - `qrImageUrl`
   - `assetUrls.qr`.

### 4.3. New docs and untracked files

1. Review untracked files:
   - `CHANGELOG.md`
   - `NEJE_DRAW_PLAN.md`
   - `firebase_flutter_integration_report.md`
   - `hermes_conversation_*.json`
   - `scripts/build-web.sh`
   - `scripts/deploy.sh`
2. Decide per file:
   - keep if Oracle-specific and useful;
   - delete/ignore if generated conversation dump;
   - do not commit generic NejeDraw docs.
3. `hermes_conversation_*.json` likely should not be committed unless user explicitly wants archive.
4. `scripts/build-web.sh` / `scripts/deploy.sh` should be checked:
   - if they duplicate existing `scripts/build_gallery_docs.sh`, prefer existing script.
   - avoid GitHub Actions/deploy automation the user previously did not want.

### 4.4. Whitespace check

1. Run:
   - `git diff --check`
2. Fix all trailing whitespace.
3. Do not use broad formatter unless it is safe and expected.

## 5. Реализовать sessionUrl / qrImageUrl после зелёных checks

### 5.1. Preconditions

1. `uv run pytest` passes.
2. `cd public_gallery && flutter analyze` has no errors.
3. `git diff --check` passes.
4. README/Firebase docs are Oracle-specific again.

### 5.2. Python uploader contract

1. In `SessionUploader._stage_public_assets`:
   - keep generated QR target as `qr.png`.
   - QR encoded payload remains `<gallery_base>/#/session/<id>`.
   - internal `record.qr_url` can remain deep link for compatibility.
2. In `FirebaseRemoteRepository.publish_session`:
   - keep upload `sessions/<id>/qr.png`.
   - compute `qr_image_url` from Storage public URL.
   - write Firestore:
     - `sessionUrl: record.qr_url`
     - `qrUrl: record.qr_url`
     - `qrImageUrl: qr_image_url`
     - `assetUrls.qr: qr_image_url`
     - `assetPaths.qr: sessions/<id>/qr.png`
3. Update manifest JSON:
   - include `sessionUrl`.
   - include `qrImageUrl`.
4. Keep backward compatibility:
   - older Flutter can still use `qrUrl` as deep link.
   - newer Flutter uses `qrImageUrl` for image.

### 5.3. Python tests

1. Update `tests/test_uploader.py`.
2. Assert staged QR exists.
3. Assert `record.qr_url` is deep link.
4. Assert remote publication payload contains:
   - `sessionUrl`
   - `qrUrl`
   - `qrImageUrl`
   - `assetUrls.qr`
5. Assert QR storage path remains:
   - `sessions/<id>/qr.png`.

### 5.4. Flutter model support

1. `SessionData` reads:
   - `sessionUrl`
   - `qrUrl`
   - `qrImageUrl`
   - fallback `assetUrls.qr`.
2. Session receipt uses:
   - `sessionUrl` for share/link/copy;
   - `qrImageUrl` if rendering QR image.
3. Do not assume `qrImageUrl` exists for old sessions:
   - fallback to `assetUrls.qr`.
4. If neither exists:
   - hide QR image UI, keep page usable.

### 5.5. Flutter page behavior

1. `/#/session/<id>` loads session doc.
2. Receipt page shows:
   - mark;
   - text;
   - measurements;
   - themes;
   - print status.
3. Add link:
   - `View in the cloth`
   - `/#/cloth?session=<id>`
4. `/cloth?session=<id>` highlights that session if visible.
5. If hidden/test session:
   - receipt can still load by direct ID.
   - cloth may show `This session is not public in the cloth`.

### 5.6. Final verification

1. Run:
   - `uv run pytest`
   - `cd public_gallery && flutter analyze`
   - `./scripts/build_gallery_docs.sh`
   - `git diff --check`
2. Manual routes:
   - `/#/`
   - `/#/cloth`
   - `/#/library`
   - `/#/marks`
   - `/#/about`
   - `/#/session/test_id`
3. Confirm QR docs:
   - `README.md`
   - `FIREBASE_SETUP.md`
   - `RUNBOOK.md` if touched.

## Acceptance Criteria

- Python tests pass fully.
- Flutter analyze has no errors.
- Project docs describe Oracle system, not generic NejeDraw.
- Flutter app is read-only against Firebase.
- `/library` remains compatible.
- QR deep link opens `/#/session/<id>`.
- QR PNG is available through Firebase Storage URL.
- Firestore distinguishes deep link and QR image:
  - `sessionUrl` / `qrUrl` for page URL.
  - `qrImageUrl` / `assetUrls.qr` for PNG.
- No visitor photos/audio/transcripts are exposed.
- Test sessions are hidden from public cloth/library.

## Assumptions

- We keep `qrUrl` as backward-compatible deep link.
- We introduce `qrImageUrl` for QR PNG.
- We do not add Firebase Auth to public gallery.
- We do not implement Flutter client writes.
- We do not change plotter/FluidNC behavior during this repair pass.
- We do not deploy to GitHub Pages until tests and analyze are green.
