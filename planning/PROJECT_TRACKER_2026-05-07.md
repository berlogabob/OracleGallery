# Oracle Project Tracker — 2026-05-07

Этот файл является единственным источником правды для текущих планов, статусов и ближайших работ проекта Oracle/NejeDraw.

## Status Vocabulary

- `[x] done` — выполнено и подтверждено кодом/проверками.
- `[~] partial` — частично выполнено, есть рабочая основа, но остаётся важный разрыв.
- `[ ] open` — не выполнено, требуется отдельная реализация.
- `[!] risk` — риск, который может сломать выставочный сценарий или дать оператору ложную уверенность.
- `[archived] superseded` — старый план/идея заменены текущим tracker-ом.

## Current Verified State

- Дата сверки: `2026-05-07`.
- `git status --short`: чисто перед консолидацией планов.
- `uv run pytest`: `79 passed`.
- `cd public_gallery && flutter analyze`: `No issues found`.
- `git diff --check`: passed.
- `/docs` остаётся только Flutter/GitHub Pages build output; planning/docs проекта туда не складываются.

## Source Files Consolidated

- `[x] done` `planning/FIX.md` — перенесён как выполненные срочные FluidNC/plotter фиксы.
- `[x] done` `planning/FIX_PLAN.md` — перенесён как детальный статус FluidNC, row printing и открытые plotter задачи.
- `[x] done` `planning/Flutter_app_update01.md` — перенесён как QR/Firebase/Flutter contract и оставшиеся UX задачи.
- `[archived] superseded` `planning/IMPLEMENTATION_PLANS.md` — общий устаревший NiceGUI/test plan, уникальные актуальные пункты перенесены в GUI open work.
- `[x] done` `planning/PLAN.md` — перенесён как current architecture snapshot.
- `[x] done` `planning/Total_fix_plan.md` — перенесён как восстановление Flutter/read-only/QR/docs baseline.
- `[archived] superseded` `planning/UPDATED_PLAN.md` — старый generic release/Firebase plan; актуальные идеи уже покрыты текущими секциями.
- `[x] done` `planning/WORK_PLAN_TODAY.md` — перенесён как плоттерный план и открытые задачи.
- `[x] done` `planning/logic_check.md` — перенесён как целевой операторский сценарий для первой ступени.

## Architecture Snapshot

- `[x] done` Mac mini в режиме выставки запускает только uploader agent; тестовая генерация допустима только из GUI/TEST mode.
- `[x] done` MacBook запускает `neje-gui`, который является главным supervisor-ом: mode, runtime state, preflight, print control, FluidNC controls, plotter daemon.
- `[x] done` Firebase используется как транспорт реальных session/plot jobs и публичных SVG/TXT/QR/manifest артефактов.
- `[x] done` Flutter Gallery на GitHub Pages является read-only витриной; QR route стабилен: `https://berlogabob.github.io/OracleGallery/#/session/<id>`.
- `[x] done` Plotter/FluidNC path: GUI/supervisor -> runtime store -> plotter daemon -> row G-code -> Telnet FluidNC sender with `ok/error/ALARM` protocol.
- `[x] done` Runtime source of truth: `runtime/oracle_runtime.sqlite3` хранит component states, selected mode, plotter config, print control, baseline, preflight result, readiness и real FluidNC arm state.
- `[~] partial` Соответствие `logic_check.md`: backend/очередь/FluidNC/G-code в основном соответствуют, но операторский сценарий и production-safe конфигурация ещё требуют доработки.

## Completed

- `[x] done` FluidNC больше не проверяется как простой open socket; probe проверяет HTTP/WebUI, Telnet, `?`, `$G`, controller state, `MPos`, `FS`, `Ov`.
- `[x] done` FluidNC sender отправляет G-code line-by-line и ждёт `ok`; `error`, `ALARM`, disconnect и timeout fail the row.
- `[x] done` GUI manual control есть: `CONNECT` with subnet auto-discovery, `Emergency Stop`, `Home`, `Home X`, `Home Y`, Jog `X/Y/Z`, `Unlock`, `Resume`, `Reset`.
- `[x] done` Manual jog/home ставит print на паузу перед движением и блокируется во время активного G-code streaming.
- `[x] done` FluidNC transport failure отключает print, disarms real mode и не помечает user jobs как `printed`.
- `[x] done` Plotter daemon переведён на row-based streaming: user jobs проверяются перед каждым рядом, user-first, idle fills remainder, current row не прерывается.
- `[x] done` Run baseline добавлен: jobs до `run_started_at` помечаются `skipped`, получают `baseline_skipped` и скрываются из print queue.
- `[x] done` Ready workflow добавлен: `Set Work Zero`, `Ready Check`, blocking `START PRINT` без preflight/work-zero/ready.
- `[x] done` `START PRINT` в real mode дополнительно блокируется без explicit arm и без FluidNC `Idle`.
- `[x] done` Test generation создаёт обычные session folders и помечает test-сессии как `origin=test`, `tags=["test","generated"]`, `visibleInLibrary=false`.
- `[x] done` Print queue берёт только `pending` jobs после baseline; старые jobs не печатаются в новом run.
- `[x] done` TinyBee workflow поддержан в коде: FluidNC `rc_servo` на оси Z, `G0 Z0` up, `G0 Z-25` down, `$H=X`, `$H=Y`, `G10 L20 P1 X0 Y0 Z0`.
- `[x] done` Preflight валидирует `assets/tinybee.json`: board XXYYZ, Telnet 23, X/Y/Z travel, X/Y single-axis homing, Z rc_servo assumptions.
- `[x] done` Rings перенесены в print-time overlay: mark SVG генерируются без baked rings, G-code рисует user single ring и idle double ring по GUI toggle.
- `[x] done` `include_rings` влияет и на preview, и на следующий G-code.
- `[x] done` Z-servo G-code включён для TinyBee touch connector: `use_z_servo=true` использует `G0/G1 Z...`; физически FluidNC мапит Z-axis на PWM servo.
- `[x] done` Runtime/GUI показывают current row, approximate current cell, row progress и sheet progress.
- `[x] done` Flutter app восстановлен как read-only public gallery; Auth/Storage/write paths удалены из Flutter.
- `[x] done` Flutter routes работают через hash routing: `/`, `/cloth`, `/library`, `/marks`, `/about`, `/session/:sessionId`, `/debug/sessions`.
- `[x] done` `/library` совместим как redirect/alias на `/cloth`.
- `[x] done` `/cloth` больше не требует Firestore composite index для visible query; фильтрация/sort выполняются в Dart.
- `[x] done` `/cloth` использует lightweight placeholder fabric вместо тяжёлого SVG composition, чтобы не фризить web app.
- `[x] done` Debug sessions page доступна через секретный control на cloth page и показывает карточки всех сессий.
- `[x] done` QR contract реализован: `sessionUrl` / `qrUrl` — deep link, `qrImageUrl` / `assetUrls.qr` — Storage PNG URL.
- `[x] done` `README.md`, `FIREBASE_SETUP.md`, `RUNBOOK.md` восстановлены как Oracle-specific docs.
- `[x] done` `docs/` очищается и пересобирается только как Flutter Pages build через `scripts/build_gallery_docs.sh`.

## Open Work

| Status | Owner | Work | Next Action |
| --- | --- | --- | --- |
| `[x] done` | `GUI` | Real workflow tabs | Вложенный `Plotter Console` заменён верхним workflow-ribbon: `Подключение`, `Калибровка`, `Тесты`, `Работа`, `Выставка`; действия разнесены по рабочим контекстам. |
| `[x] done` | `plotter` | Exact cell progress | Runtime current cell теперь считается по `; cell-start` markers, преобразованным в пороги acknowledged FluidNC commands, а не по грубой доле строки. |
| `[ ] open` | `plotter` | `PrintRow` / `PrintCell` models | Вынести row/cell assembly из `PlotterDaemon.run_cycle()` в pure helper и manifest schema через явные dataclasses. |
| `[x] done` | `GUI` | Queue dashboard counts | GUI показывает read-only queue counts: pending after baseline, active leased/plotting, failed/skipped, online/offline; idle printing не зависит от Firebase status. |
| `[x] done` | `plotter` | Working Z-axis baseline | Confirmed on hardware 2026-05-13: `NEJE_PLOTTER_USE_Z_SERVO=true`, `Z+` sends `G21/G90/G54/G0 Z0`, `Z-` sends `G21/G90/G54/G0 Z-25`; no `$J Z...`, no `M3/M5`, no auto-probe after manual Z. |
| `[~] partial` | `docs` | One-page operator runbook | RUNBOOK покрывает FluidNC/manual control, но нужен короткий окончательный порядок выставки: hotspot -> GUI -> CONNECT -> baseline -> calibration -> ready -> print -> reload. |
| `[ ] open` | `Firebase` | Normalization handoff on MacBook | Реализовать pipeline: download raw SVG from Firebase -> normalize with current GUI scales -> upload normalized `artwork.svg` -> release print job. |
| `[ ] open` | `Flutter` | Final visual polish | Завершить дизайн по Oracle direction: cloth/fabric presentation, marks, about, receipt polish, without reintroducing freezes. |
| `[~] partial` | `GUI` | MacBook 14-inch fit | Основной экран переведён на фиксированный top-ribbon + локальный scroll внутри side panels; требуется визуальная проверка на реальном 14-inch экране. |
| `[x] done` | `plotter` | Final post-sheet safety command | После завершения рядов daemon отправляет отдельный `*_sheet_end.gcode`: `Z up` + `G0 X0 Y0`, затем переходит в reload pause. |
| `[ ] open` | `Firebase` | Deploy queue index | Проверить/задеплоить Firestore index `plot_jobs(status, createdAt)` перед реальной выставочной очередью. |
| `[x] done` | `plotter` | Supervisor cleanup | Старые неиспользуемые helper methods с несуществующими зависимостями удалены из `SupervisorService`. |
| `[x] done` | `GUI` | Ready workflow copy | Ready tab содержит явный physical checklist: paper fixed, upper-left work origin, manual Z/contact/pen pressure, then `Set Work Zero`; software cannot verify pressure. |

## Risks

- `[!] risk` TinyBee touch connector uses FluidNC Z-axis commands for PWM servo. This is a confirmed working baseline; do not refactor it back to `$J Z...` or `M3/M5`.
- `[!] risk` Firestore queue queries зависят от индекса `plot_jobs(status, createdAt)`; индекс есть в repo, но должен быть deployed в Firebase.
- `[!] risk` GUI теперь разделён top-level workflow-вкладками, но плотность отдельных panels нужно проверить на реальном MacBook 14-inch и при необходимости ещё сократить.
- `[!] risk` Physical emergency stop не заменяется GUI `Emergency Stop`; software feed hold `!` — только дополнительный уровень безопасности.
- `[!] risk` Ready workflow не может физически проверить давление пера и реальный Z-contact; это остаётся операторским действием перед `Set Work Zero`.

## Today Plan 2026-05-07

### A. Consolidate Planning Files

- `[x] done` Inventory all files under `planning/`.
- `[x] done` Classify source files into plotter/FluidNC, Flutter/QR/Firebase, architecture snapshot, superseded generic plans.
- `[x] done` Create this consolidated tracker as the only planning entrypoint.
- `[x] done` Preserve current verified checks and important operator decisions.
- `[x] done` Mark stale generic plans as `[archived] superseded`.
- `[x] done` Delete old source planning files after consolidation.
- `[x] done` Run `git diff --check` after deletion.
- `[x] done` Confirm only this file remains in `planning/`.

### B. Next Implementation Priority

- `[~] partial` First: fix production plotter reliability and operator flow, not Flutter polish.
- `[x] done` Make GUI panels truly step-based: top-level `Подключение`, `Калибровка`, `Тесты`, `Работа`, `Выставка`.
- `[x] done` Implement exact marker-aware cell progress and queue dashboard.
- `[~] partial` Decide and validate production Z-servo config on real hardware.
- `[x] done` Add explicit post-sheet safety command: `Z up`, `G0 X0 Y0`, then `paused_for_reload`.
- `[ ] open` Deploy/verify Firestore queue index for `plot_jobs(status, createdAt)`.
- `[x] done` Remove stale unused `SupervisorService` validation helpers.
- `[ ] open` Then implement Firebase normalization handoff.
- `[ ] open` Then return to Flutter visual polish.

## Acceptance Criteria

- `[x] done` `planning/` contains only `PROJECT_TRACKER_2026-05-07.md`.
- `[x] done` Every active open item has owner area: `plotter`, `GUI`, `Firebase`, `Flutter`, or `docs`.
- `[x] done` No conflicting statuses remain from old plans.
- `[x] done` `git diff --check` passes.
- `[x] done` `git status --short planning` shows one new tracker and nine deleted old planning files.
- `[x] done` A future engineer can continue work without opening any removed plan files.

## Manual Operator Scenario Target

1. Operator starts phone hotspot.
2. MacBook connects to hotspot.
3. Plotter powers on and joins hotspot.
4. Operator runs `uv run neje-gui`.
5. Operator presses `CONNECT`; GUI auto-discovers FluidNC on the current hotspot subnet and shows HTTP online, Telnet online, controller `Idle`.
6. `START SYSTEM` records `run_started_at`; old pending jobs are skipped/baseline-hidden.
7. In `TEST`, live generator may create fake user sessions with hidden test tags.
8. Operator fixes paper, jogs to upper-left work zero, adjusts Z/contact physically, presses `Set Work Zero`.
9. `Ready Check` raises Z, homes X/Y, returns to work zero and requires `Idle`.
10. `Start Print` begins row-based printing only after preflight/readiness/safety gates.
11. User jobs print first at next row boundary; idle symbols fill empty cells.
12. Rings reflect GUI toggle at print time.
13. End of sheet leaves Z up, returns X/Y to work zero/home-safe position and waits for `Reload OK`.

## Assumptions

- Old planning files are removed, not archived.
- This tracker is documentation/planning only; no production code behavior is changed by this consolidation.
- Existing verified baseline remains valid unless code changes after this file.
- Mac mini remains simple and safe in exhibition: uploader only, no autonomous generation unless explicitly controlled in TEST mode.
