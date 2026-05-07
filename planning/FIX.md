# Срочные фиксы: статус

Обновлено: 2026-05-05

## Выполнено

- [x] Составлен и сохранён рабочий план исправлений в `FIX_PLAN.md`.
- [x] FluidNC больше не проверяется как простой `socket open`.
- [x] Добавлены явные настройки FluidNC:
  - `NEJE_PLOTTER_FLUIDNC_HTTP_URL=http://10.198.21.74`
  - `NEJE_PLOTTER_FLUIDNC_TELNET_HOST=10.198.21.74`
  - `NEJE_PLOTTER_FLUIDNC_TELNET_PORT=23`
  - `NEJE_PLOTTER_FLUIDNC_CONNECT_TIMEOUT_SECONDS=3`
  - `NEJE_PLOTTER_FLUIDNC_ACK_TIMEOUT_SECONDS=10`
- [x] Добавлен FluidNC probe:
  - HTTP/WebUI check;
  - Telnet check;
  - status `?`;
  - modal state `$G`;
  - parse `Idle/Run/Hold/Alarm/Sleep/Unknown`;
  - parse `MPos`, `FS`, `Ov`.
- [x] G-code sender больше не отправляет строки вслепую:
  - ждёт `ok`;
  - падает на `error`, `ALARM`, disconnect, timeout;
  - считает progress по подтверждённым строкам.
- [x] Добавлено управление плоттером из GUI:
  - `Connect / Probe`;
  - `Emergency Stop`;
  - `Home`;
  - `Home X`;
  - `Home Y`;
  - `Jog X/Y`;
  - `Unlock`;
  - `Resume`;
  - `Reset`.
- [x] Ручной jog/home ставит печать на паузу перед движением.
- [x] Ручной jog/home блокируется во время активного G-code streaming.
- [x] При FluidNC error/timeout job не помечается как `printed`; real mode disarm, print disabled.
- [x] Plotter daemon переведён с whole-sheet G-code streaming на row-based streaming:
  - layout группируется по рядам;
  - перед каждым рядом заново читается user queue;
  - user jobs имеют приоритет на ближайшем следующем ряду;
  - idle symbols добивают пустые места ряда;
  - текущий ряд не прерывается;
  - после завершения листа всё ещё требуется reload confirmation.
- [x] GUI progress теперь показывает row progress: `current row / total rows`, G-code lines текущего ряда и общий sheet percent.
- [x] Добавлен run baseline: jobs до `run_started_at` помечаются `skipped`, получают tag `baseline_skipped` и скрываются из print queue.
- [x] Добавлен Ready workflow: `Set Work Zero`, `Ready Check`, блокировка `START PRINT` без preflight/work-zero/ready.
- [x] Добавлена поддержка TinyBee Z-servo G-code: `Z0=down`, `Z25=up`, `G10 L20 P1 X0 Y0 Z0`, `$H=X`, `$H=Y`.
- [x] Preflight валидирует `assets/tinybee.json`: board XXYYZ, Telnet 23, X/Y/Z travel, X/Y single-axis homing, Z rc_servo.
- [x] Rings перенесены в print-time overlay: SVG генерируются mark-only, а G-code рисует ring(s) по GUI toggle.
- [x] Preview подсвечивает текущий ряд по runtime state.
- [x] Preview подсвечивает текущую ячейку по runtime state.
- [x] GUI plotter block упрощён в один `Plotter Console` с порядком:
  - `1. Connect`;
  - `2. Manual control`;
  - `3. Print`.
- [x] Из верхней панели удалены дублирующие plotter/print кнопки.
- [x] Удалена строка дублирующих status pills.
- [x] Jog steps изменены на `1`, `5`, `10`, `25`, `50`, `100 mm`.
- [x] `README.md` и `RUNBOOK.md` обновлены по FluidNC, Telnet, emergency stop и manual control.

## Частично выполнено

- [~] В `TEST` режиме теперь есть FluidNC diagnostics, dry-run, manual control и test generation. Полная отдельная логика “test-send real tiny job” пока не добавлена намеренно, чтобы не создавать опасную кнопку.
- [~] GUI стал понятнее в plotter части, но общий интерфейс ещё не полностью переразложен на “hardware слева / symbols справа”. Это отложено, потому что сейчас фокус только на plotter/G-code/FluidNC.

## Не выполнено / на паузе

- [ ] Firebase normalization handoff на MacBook: raw SVG -> normalize with GUI scales -> upload normalized -> release print job.
- [ ] Полноценный UX-tab layout вместо текущего компактного ribbon + panels.
- [ ] Flutter app по `assets/WebsiteWireframe`.
- [ ] Видео `https://youtu.be/kMwNTh0pS1k` на сайте.

## Оригинальные проблемы из `FIX.md`

- [x] “FluidNC не находится, хотя открыт dashboard `http://10.198.21.74/#/dashboard`” — исправлено на уровне config/probe/GUI diagnostics. HTTP online больше не считается достаточным для sender-а; нужен Telnet + `Idle`.
- [~] “В TEST mode нет возможности подключаться к плоттеру” — исправлено для diagnostics/manual control; physical print остаётся safety-gated.
- [~] “GUI непонятно как пользоваться” — plotter часть упорядочена; остальная GUI-структура остаётся следующим UX-этапом.
- [x] “Печать рядами, а не целым листом” — базовая row-based версия выполнена. Следующий UX-шаг: подсветка текущего ряда в preview.
- [ ] “MacBook нормализует SVG из Firebase и подменяет обратно” — не выполнено.
- [ ] “Flutter website по WebsiteWireframe” — не выполнено.
