# Test Symbol Generator + Complete Run Documentation

## Summary
- Добавить генератор тестовых Oracle-сессий, который имитирует TouchDesigner: создаёт реальные папки с `*_plotter.svg`, `*_receipt.txt`, `READY` и строкой в `session_log.csv`.
- По выбранному варианту генератор по умолчанию пишет в реальную `NEJE_UPLOADER_SESSION_ROOT`, чтобы сразу проверять auto-upload в Firebase и создание `plot_jobs`.
- Добавить отдельную генерацию idle/filling SVG для запасной очереди плоттера: те же 8 базовых символов, но с двойной окружностью.
- Обновить документацию в формате `README.md` + отдельный root `RUNBOOK.md`, потому что `docs/` занят Flutter Pages build output.

## Key Changes
- Добавить Python CLI `neje-generate-sessions`.
- CLI режимы:
  - `--mode user`: создаёт пользовательские session folders с одним кругом, receipt TXT, READY marker, CSV measures.
  - `--mode idle`: создаёт локальный idle symbol bank с двойным кругом для плоттера, без Firebase и без `plot_jobs`.
  - `--live --interval-seconds N`: создаёт пользовательские сессии по одной с интервалом, чтобы проверять реальный auto-upload при запущенном uploader.
- Источник символов: `assets/symbols/*.svg`.
- Output defaults:
  - user sessions: `NEJE_UPLOADER_SESSION_ROOT`, fallback `assets/sessions`.
  - idle symbols: `assets/generated_idle_symbols`.
- SVG output:
  - нормализованный `viewBox="0 0 800 800"`;
  - базовый символ центрируется внутри окружности;
  - user SVG получает одну окружность;
  - idle SVG получает две окружности;
  - окружность включается в bbox, поэтому при печати внешний круг становится фактическим `NEJE_PLOTTER_MARK_DIAMETER_MM`.
- Scale control:
  - добавить `assets/symbols/symbol_scales.json`;
  - ключи: basename каждого из 8 исходных SVG;
  - значение: scale multiplier для самого знака внутри окружности, не для окружности;
  - default для всех: `1.0`.
- Variation control:
  - jitter линий зависит от seed и synthetic measures;
  - intensity/instability/confidence пишутся в `session_log.csv`, чтобы uploader добавил их в Firestore;
  - receipt TXT остаётся в существующем формате, который уже парсит uploader.
- Launch wrappers:
  - `generate_test_sessions.command` и `.sh` в root;
  - `assets/sessions/GENERATE_TEST_SESSION.command` для запуска прямо из реальной папки сессий на Mac mini;
  - wrapper показывает output path, количество созданных сессий и предупреждает, что при активном uploader они сразу уйдут в Firebase.
- Plotter launcher:
  - если `assets/generated_idle_symbols` существует и содержит SVG, использовать его как default `NEJE_PLOTTER_PLACEHOLDER_ROOT`;
  - иначе fallback остаётся `assets/symbols`.

## Documentation Updates
- `README.md`: оставить короткий обзор архитектуры, контракты, основные команды, список launchers.
- `RUNBOOK.md`: добавить пошаговые инструкции:
  - первая установка на Oracle Mac mini;
  - запуск uploader из `assets/sessions`;
  - проверка Firebase upload и Firestore `plot_jobs`;
  - генерация тестовых пользовательских сессий;
  - live генерация для проверки real-time priority;
  - генерация idle bank с двойными кругами;
  - запуск plotter daemon в dry-run и real mode;
  - где смотреть spool, G-code, operator dashboard;
  - сборка Flutter в `/docs`;
  - применение Firebase rules, indexes и Storage CORS;
  - troubleshooting: CORS, credentials, неверный watched folder, повторный import, пустая очередь.
- `public_gallery/README.md`: обновить описание под текущий digital receipt UI без фото/preview.

## Test Plan
- Unit tests для генератора:
  - создаёт session folder с `{id}_plotter.svg`, `{id}_receipt.txt`, `READY`;
  - append/update `session_log.csv` без transcript/photo/audio;
  - user SVG содержит одну окружность;
  - idle SVG содержит две окружности;
  - per-symbol scale меняет bbox знака, но не меняет внешний круг;
  - output SVG читается текущим `svg_gcode`.
- Integration-style local test:
  - сгенерировать 1 user session в temp sessions root;
  - запустить `SessionUploader.scan_once()` с fake remote;
  - проверить, что создаётся `plot_jobs` payload через существующий publish path.
- Existing checks:
  - `uv run pytest`;
  - `cd public_gallery && flutter analyze`;
  - `./scripts/build_gallery_docs.sh`.

## Assumptions
- Генератор не пишет напрямую в Firebase. Это намеренно: он проверяет настоящий путь `folder -> uploader -> Firebase -> plot_jobs`.
- Тестовые сессии будут видны в публичной витрине, если uploader запущен и output path указывает на реальную watched-папку.
- Оригинальные 8 SVG в `assets/symbols` не перезаписываются; все вариации и idle SVG создаются отдельно.
