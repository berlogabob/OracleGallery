# Oracle GUI v2: текущий план и состояние

## Summary

`neje-gui` является главным операторским пультом выставочной системы. Из него оператор выбирает режим, запускает supervised system, запускает preflight, смотрит статусы, управляет Mac mini uploader agent, контролирует plotter daemon, подтверждает reload и включает печать.

Система намеренно безопасна по умолчанию: при открытии GUI ничего не стартует автоматически, physical FluidNC output заблокирован до явного режима `EXHIBITION REAL`, успешного preflight и ручного `ARM REAL FLUIDNC`.

## Реализованная архитектура

- **Mac mini / TouchDesigner:** TouchDesigner только создаёт session folders. В реальной sessions-папке Mac mini есть один операторский файл `START_ORACLE_UPLOADER.command`; он делает setup при необходимости и запускает только `neje-uploader-agent`.
- **MacBook / Operator + Plotter:** `neje-gui` запускает локальный `PlotterDaemon` в background thread через `SupervisorService`.
- **Runtime source of truth:** `runtime/oracle_runtime.sqlite3` хранит component states, plotter config, print control, selected system mode, preflight result и real FluidNC arm state.
- **Logs:** supervisor/preflight/uploader/plotter actions пишутся в `logs/oracle_supervisor.log`, путь задаётся `NEJE_ORACLE_LOGS_ROOT`.
- **Legacy launchers:** `neje-uploader` и `neje-plotter` остаются backup/debug path, но выставочный путь: `neje-uploader-agent` + `neje-gui`.
- **FluidNC transport:** `FluidNCTransport` проверяет HTTP/WebUI, Telnet, status `?`, modal `$G`, парсит состояние контроллера и отправляет G-code только с ожиданием `ok`.
- **Plotter Console:** управление плоттером в GUI собрано в последовательность `Connect`, `Manual control`, `Print`.
- **Row-based plot streaming:** `PlotterDaemon` больше не стримит один большой G-code на весь лист. Он группирует layout по рядам, перед каждым рядом заново проверяет user queue, добивает ряд idle-symbols и стримит отдельный row G-code.
- **Run baseline:** при `START SYSTEM` создаётся `run_started_at`, старые pending jobs помечаются `skipped/baseline_skipped` и не попадают в новую печать.
- **Ready workflow:** перед `START PRINT` требуется `Set Work Zero` и `Ready Check`; для TinyBee Z-servo поддержаны `Z0=down`, `Z25=up`, `$H=X`, `$H=Y`, `G10 L20 P1 X0 Y0 Z0`.

## GUI modes

- `TEST`: fake sessions, idle bank, preview, dry-run sheet. Physical FluidNC output заблокирован.
- `EXHIBITION DRY`: реальные sessions/uploader/Firebase/queue, но output остаётся dry-run/spool.
- `EXHIBITION REAL`: реальные sessions + FluidNC. `START PRINT` разрешается только после `PREFLIGHT` без critical failures и `ARM REAL FLUIDNC`.

Внутренние поля `run_mode` и `dry_run` сохраняются для совместимости plotter daemon, но оператор больше не управляет ими как независимыми переключателями.

## Operator workflow

1. Запустить `assets/sessions/START_ORACLE_UPLOADER.command` на Mac mini.
2. Запустить `neje-gui` на operator/plotter MacBook.
3. Выбрать режим: `TEST`, `EXHIBITION DRY` или `EXHIBITION REAL`.
4. Нажать `START SYSTEM`.
5. В `Plotter Console` нажать `Connect / Probe`; FluidNC должен показать HTTP online, Telnet online и state `Idle`.
6. Нажать `Preflight`.
7. В `TEST` или `EXHIBITION DRY` можно нажать `Start Print`; физическая отправка в FluidNC заблокирована.
8. Jog-ом поставить инструмент в левый верхний рабочий ноль, нажать `Set Work Zero`, затем `Ready Check`.
9. В `EXHIBITION REAL` после successful preflight нажать `Arm Real`, затем `Start Print`.
10. Для обычной остановки использовать `Stop After Sheet`; это не emergency stop и не рвёт текущий row G-code stream. Для аварийной остановки использовать `Emergency Stop` и физическую кнопку питания/аварийный стоп.

## Реализованные safety gates

- Mode change всегда сбрасывает `real_fluidnc_armed=false`.
- `START PRINT` в `EXHIBITION REAL` блокируется без arm.
- `START PRINT` во всех режимах блокируется без successful preflight, work zero и ready check.
- `ARM REAL FLUIDNC` блокируется без preflight result или при critical failures.
- `ARM REAL FLUIDNC` проверяет FluidNC online и `Idle` перед arming.
- `TEST` и `EXHIBITION DRY` всегда мапятся в dry-run control state.
- `EMERGENCY STOP` отправляет realtime feed hold `!`, выключает `print_enabled` и disarm real mode.
- Manual jog/home ставит print на паузу перед движением и блокируется во время активного G-code streaming.
- Любой FluidNC transport failure отключает print, disarm real mode и не помечает jobs как `printed`.
- User jobs обновляются как `plotting/printed` только после успешного row stream; при ошибке текущий row-job получает `failed`.
- Generated/uploaded SVGs теперь mark-only; rings рисуются в G-code как print-time overlay по `include_rings`.

## Preflight

Preflight проверяет:

- runtime folder writable;
- base symbols available;
- generated idle bank present или warning fallback;
- uploader watched folder;
- Firebase config;
- FluidNC HTTP/WebUI, Telnet, `?` status, `$G` modal state, controller `Idle`;
- spool folder writable;
- dry-run G-code generation.

Результат сохраняется в runtime store и отображается в `Plotter Console`, logs и runtime state.

## Следующие этапы

- **Queue dashboard:** показывать реальные counts Firestore `plot_jobs`: pending, leased, plotting, printed, failed, retry.
- **Uploader outbox/quarantine:** durable local backlog на Mac mini для плохой сети и битых sessions.
- **Preflight depth:** добавить реальный Firebase read/write smoke test вместо проверки только конфигурации.
- **Row preview depth:** текущий ряд и приблизительная текущая ячейка уже подсвечиваются в preview; следующий шаг — exact per-symbol transport events вместо line-fraction estimate.
- **TinyBee validation:** preflight уже проверяет `assets/tinybee.json`; следующий шаг — подтягивать live machine config напрямую из FluidNC, если WebUI/API позволит.
- **Firebase normalization handoff:** MacBook должен скачивать raw SVG из Firebase, нормализовать с GUI scales, заливать normalized SVG обратно и только потом выпускать job в печать.
- **FluidNC progress depth:** текущий progress уже основан на подтверждённых `ok`; следующий уровень — отображать controller status during stream.
- **GUI modularization phase 2:** вынести panel composition из `gui_service.py` в отдельные panel-модули. Текущий UI kit уже вынесен, но основной page composition пока оставлен в одном файле для снижения риска.
- **Flutter WebsiteWireframe:** отложено до завершения plotter/G-code work.

## Verification

Обязательные проверки после изменений:

```bash
uv run pytest
cd public_gallery && flutter analyze
./scripts/build_gallery_docs.sh
```

Текущий тестовый набор покрывает mode mapping, preflight, real FluidNC safety gate, runtime store, supervisor start/stop, uploader agent, GUI settings, SVG normalization, FluidNC probe/ack streaming/control commands, row grouping и row-based plotter streaming.
