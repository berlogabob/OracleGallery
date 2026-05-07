# План работ на сегодня: финализация плоттерной части Oracle

## Summary

Создать в корне проекта файл `WORK_PLAN_TODAY.md` и зафиксировать в нём пошаговый план работ на сегодня. Цель дня: довести плоттерную часть до понятного операторского workflow в `neje-gui`: `Connection -> Calibration -> Ready -> Exhibition`, точный прогресс печати по ряду/ячейке, понятная очередь jobs, и усиленная проверка FluidNC/TinyBee перед реальной печатью.

Работа ограничена плоттером, GUI управления, runtime state, FluidNC, queue visibility и документацией. Flutter не трогать. Firebase normalization handoff описать как следующий этап, но не смешивать с сегодняшней плоттерной задачей.

## Файл плана

- Создать файл `/Users/berloga/Documents/GitHub/NejeDraw/WORK_PLAN_TODAY.md`.
- В начале файла указать дату: `2026-05-06`.
- В файле использовать чекбоксы `[ ]`, `[~]`, `[x]`, чтобы его можно было обновлять по ходу дня.
- Не заменять `PLAN.md`, `FIX.md`, `FIX_PLAN.md`; новый файл должен быть рабочим дневным планом, а не общей архитектурной документацией.

## Шаги Работы

### 1. Зафиксировать текущее состояние

1. Проверить `git status --short`.
2. Убедиться, что текущие незакоммиченные изменения не конфликтуют с новым планом.
3. Зафиксировать в `WORK_PLAN_TODAY.md`, что уже готово:
   - [x] FluidNC HTTP/Telnet probe.
   - [x] Telnet streaming с ожиданием `ok`.
   - [x] Emergency Stop / Hold / Resume / Soft Reset.
   - [x] Jog X/Y/Z.
   - [x] Set Work Zero.
   - [x] Ready Check.
   - [x] Z-servo G-code.
   - [x] Row-based печать.
   - [x] Baseline skip для старых jobs.
   - [x] Подсветка текущего ряда и приблизительной текущей ячейки.
   - [x] Preflight по `assets/tinybee.json`.
4. Зафиксировать, что Flutter и публичная витрина сегодня вне scope.

### 2. Переразложить GUI в понятный workflow

1. [x] Нашел текущую композицию GUI в `gui_service.py`
2. [x] Перестроил GUI на явные вкладки (Connection, Calibration, Ready, Exhibition)
3. [ ] Добавить точный прогресс по ячейке через G-code маркеры
4. [ ] Dashboard очереди заданий (Firebase counts)
5. [ ] Усиление валидации FluidNC/TinyBee
6. [ ] Обновление RUNBOOK.md
7. [ ] Написание unit-тестов
8. [ ] Проверка работоспособностийти текущую композицию `neje-gui` в `src/neje_oracle/gui_service.py`.
2. Оставить backend callbacks существующими, не переписывать supervisor/daemon без необходимости.
3. Сделать реальные вкладки или ribbon-панели:
   - `1 Connection`
   - `2 Calibration`
   - `3 Ready`
   - `4 Exhibition`
4. `Connection` должен содержать только:
   - FluidNC probe.
   - WebUI/Telnet/status `$G`.
   - Controller state.
   - Emergency Stop.
   - Unlock Alarm.
   - Resume Hold.
   - Soft Reset.
5. `Calibration` должен содержать:
   - Jog X/Y/Z.
   - Jog step `1 / 5 / 10 / 25 / 50 / 100`.
   - Layout mode `hex/grid`.
   - Width/height/margin/cell/gap.
   - Rings toggle.
   - Scale controls.
   - Calibration preview with symbols.
   - Dry-run sheet generation.
6. `Ready` должен содержать:
   - Work zero state.
   - `Set Work Zero`.
   - `Ready Check`.
   - Preflight result.
   - TinyBee hardware check result.
   - Clear blocking reason if `START PRINT` is unavailable.
7. `Exhibition` должен содержать только:
   - Queue summary.
   - Sheet preview as cells/rings, not full calibration symbol view.
   - Start Print.
   - Stop After Sheet.
   - Reload OK.
   - Emergency Stop.
   - Current row/cell/progress.
8. В `TEST` режиме показывать generator и idle bank только в `Calibration`.
9. В `EXHIBITION DRY` и `EXHIBITION REAL` скрыть или disable test generation.
10. Проверить, что главный экран помещается на MacBook 14 без общего вертикального скролла; допустим скролл внутри отдельных панелей.
   - [~] В процессе

### 3. Ввести явные модели PrintRow / PrintCell

1. Добавить dataclass `PrintCell`:
   - `sheet_index`
   - `row_index`
   - `cell_in_row`
   - `center_x_mm`
   - `center_y_mm`
   - `diameter_mm`
   - `source_kind`
   - `session_id`
   - `title`
   - `svg_path`
2. Добавить dataclass `PrintRow`:
   - `row_index`
   - `row_id`
   - `cells`
   - `status`
   - `gcode_path`
   - `error`
3. Перенести row assembly из `PlotterDaemon.run_cycle()` в отдельную pure/helper функцию.
4. Сохранить текущее поведение:
   - user jobs берутся перед каждым рядом;
   - user jobs ставятся первыми;
   - idle symbols добивают остаток ряда;
   - текущий ряд не прерывается;
   - sheet reload остаётся после последнего ряда.
5. Обновить manifest, чтобы строки и ячейки писались через `PrintRow / PrintCell`.
6. Сохранить backward compatibility чтения старых manifest, если GUI читает последние spool файлы.
   - [ ]

### 4. Сделать точный progress по ячейке

1. При генерации G-code добавить явные комментарии-маркеры:
   - `; cell-start <sheet_index> <session_id>`
   - `; cell-end <sheet_index> <session_id>`
2. Обновить transport/daemon progress так, чтобы runtime state обновлял текущую ячейку по этим маркерам, а не по приблизительной доле строк.
3. Сохранить acknowledged-line progress как отдельный показатель.
4. Runtime state должен показывать:
   - current sheet;
   - current row;
   - current cell;
   - current session id;
   - row progress;
   - sheet progress;
   - acknowledged G-code lines.
5. GUI preview должен подсвечивать:
   - текущий ряд;
   - текущую ячейку;
   - завершённые ячейки более спокойным стилем;
   - failed row/cell при ошибке.
6. В `Exhibition` preview не рисует все символы; показывает cells/rings/progress.
7. В `Calibration` preview оставляет полный символный вид для настройки scale.
   - [ ]

### 5. Добавить Queue Dashboard в GUI

1. Добавить backend метод в Firebase repository для чтения counts `plot_jobs`.
2. Считать минимум:
   - pending;
   - leased;
   - plotting;
   - printed;
   - failed;
   - skipped;
   - hidden/visibleInQueue=false.
3. Добавить GUI queue block в `Exhibition`.
4. Показать:
   - сколько user jobs ждёт;
   - сколько печатается;
   - сколько failed;
   - сколько было skipped by baseline.
5. Добавить кнопку `Refresh Queue`.
6. Не добавлять опасные массовые actions вроде `clear all jobs` в этом этапе.
7. Если Firebase недоступен, GUI должен показывать `queue offline`, а печать idle symbols должна продолжать работать.
   - [ ]

### 6. Усилить FluidNC/TinyBee validation

1. Оставить текущий preflight по локальному `assets/tinybee.json`.
2. Добавить отдельный GUI статус `TinyBee config`.
3. Если возможно через FluidNC HTTP/WebUI API без риска, добавить read-only live config probe.
4. Если live config недоступен, явно показывать:
   - `Using local tinybee.json export`
   - timestamp или path файла
   - warning, что файл должен соответствовать реальному контроллеру.
5. Preflight должен блокировать `EXHIBITION REAL`, если:
   - Telnet disabled или порт не 23;
   - board не `MKS TinyBee V1.0 XXYYZ`;
   - X/Y travel меньше рабочей области;
   - Z travel меньше `z_up_mm`;
   - X/Y single-axis homing выключен;
   - Z rc_servo отсутствует.
6. Документировать, что HTTP dashboard online не равен готовности sender-а.
   - [ ]

### 7. Обновить операторский сценарий

1. В `RUNBOOK.md` добавить короткий сценарий “сегодняшний реальный порядок работы”:
   - включить hotspot;
   - подключить MacBook;
   - включить плоттер;
   - запустить `uv run neje-gui`;
   - `Connection -> Probe`;
   - `Calibration -> Jog / Layout / Dry-run`;
   - `Ready -> Set Work Zero -> Ready Check`;
   - `Exhibition -> Start Print`;
   - `Stop After Sheet` или `Emergency Stop`.
2. В `PLAN.md` отметить выполненные пункты после реализации.
3. В `FIX_PLAN.md` обновить статусы:
   - GUI workflow tabs;
   - PrintRow/PrintCell;
   - exact cell progress;
   - queue dashboard;
   - TinyBee live/local validation.
4. Не обновлять Flutter docs в этом этапе.
   - [ ]

### 8. Тесты и Проверки

1. Добавить unit tests для `PrintRow / PrintCell` assembly:
   - user jobs идут перед idle;
   - late user job попадает в следующий ряд;
   - empty user queue печатает idle row.
2. Добавить tests для G-code markers:
   - каждый cell имеет `cell-start` и `cell-end`;
   - markers не отправляются как motion commands;
   - progress parser корректно обновляет current cell.
3. Добавить tests для runtime state:
   - current row/cell/session обновляются во время stream;
   - failed row не помечает job printed;
   - Stop After Sheet не прерывает текущий ряд.
4. Добавить tests для queue dashboard:
   - counts считаются по status;
   - Firebase unavailable даёт warning/offline state, не crash.
5. Добавить tests для GUI support:
   - preview подсвечивает текущий ряд;
   - preview подсвечивает текущую ячейку;
   - Exhibition preview не зависит от full symbol drawing.
6. Запустить:
   - `uv run python -m py_compile src/neje_oracle/*.py`
   - `uv run pytest`
   - `git diff --check`
7. Flutter checks сегодня не обязательны, если Flutter files не менялись.
   - [ ]

## Acceptance Criteria

- Оператор может пройти весь путь в GUI слева направо: `Connection -> Calibration -> Ready -> Exhibition`.
- `START PRINT` остаётся заблокированным без preflight, work zero и ready state.
- `EXHIBITION REAL` остаётся заблокированным без successful preflight и `ARM REAL FLUIDNC`.
- Печать идёт по рядам, user jobs проверяются перед каждым рядом.
- Preview показывает текущий ряд и точную текущую ячейку по G-code cell markers.
- Queue dashboard показывает реальные counts или понятное offline состояние.
- Ошибка FluidNC отключает print, disarm real mode и не помечает job printed.
- После полного листа Z поднят, X/Y возвращены в work zero, состояние переходит в `paused_for_reload`.
- `uv run pytest` проходит полностью.

## Assumptions

- Сегодня не делаем Flutter app и WebsiteWireframe.
- Сегодня не делаем полный Firebase normalization handoff; он остаётся следующим отдельным этапом.
- `Stop After Sheet` остаётся мягкой остановкой перед следующим листом; аварийная остановка остаётся `Emergency Stop`/feed hold и физическая кнопка.
- Live FluidNC config reading добавляется только если есть read-only безопасный способ; иначе GUI явно показывает, что используется локальный `assets/tinybee.json`.
- Реальная отправка в FluidNC остаётся opt-in через `EXHIBITION REAL` и `ARM REAL FLUIDNC`.
