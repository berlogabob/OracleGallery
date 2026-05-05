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
5. Нажать `PREFLIGHT`.
6. В `TEST` или `EXHIBITION DRY` можно нажать `START PRINT`; физическая отправка в FluidNC заблокирована.
7. В `EXHIBITION REAL` после successful preflight нажать `ARM REAL FLUIDNC`, затем `START PRINT`.
8. Для остановки использовать `STOP AFTER SHEET`; это не emergency stop и не рвёт текущий G-code stream.

## Реализованные safety gates

- Mode change всегда сбрасывает `real_fluidnc_armed=false`.
- `START PRINT` в `EXHIBITION REAL` блокируется без arm.
- `ARM REAL FLUIDNC` блокируется без preflight result или при critical failures.
- `ARM REAL FLUIDNC` проверяет FluidNC online перед arming.
- `TEST` и `EXHIBITION DRY` всегда мапятся в dry-run control state.

## Preflight

Preflight проверяет:

- runtime folder writable;
- base symbols available;
- generated idle bank present или warning fallback;
- uploader watched folder;
- Firebase config;
- FluidNC connection;
- spool folder writable;
- dry-run G-code generation.

Результат сохраняется в runtime store и отображается в GUI status strip/logs.

## Следующие этапы

- **Queue dashboard:** показывать реальные counts Firestore `plot_jobs`: pending, leased, plotting, printed, failed, retry.
- **Uploader outbox/quarantine:** durable local backlog на Mac mini для плохой сети и битых sessions.
- **Preflight depth:** добавить реальный Firebase read/write smoke test вместо проверки только конфигурации.
- **FluidNC progress:** перейти от локального G-code line progress к подтверждениям/статусу FluidNC, если транспорт позволит.
- **GUI modularization phase 2:** вынести panel composition из `gui_service.py` в отдельные panel-модули. Текущий UI kit уже вынесен, но основной page composition пока оставлен в одном файле для снижения риска.

## Verification

Обязательные проверки после изменений:

```bash
uv run pytest
cd public_gallery && flutter analyze
./scripts/build_gallery_docs.sh
```

Текущий тестовый набор покрывает mode mapping, preflight, real FluidNC safety gate, runtime store, supervisor start/stop, uploader agent, GUI settings, SVG normalization и plotter G-code helpers.
