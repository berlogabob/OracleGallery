# Task 2: Исправить mypy ошибки в live Python path

## Цель
Сократить количество mypy ошибок с 65 до 0 (после CI job добавления stub-аннотаций)

## Файлы
- `src/neje_oracle/gui_service.py` — 63 ошибки (основная проблема)
- `src/neje_oracle/config.py` — 1 ошибка (return type)
- `src/neje_oracle/session_uploader.py` — 1 ошибка (optional float)
- `src/neje_oracle/transport.py` — 1 ошибка (tuple narrowing)
- `src/neje_oracle/firebase_io.py` — 1 ошибка (assignment type)
- `src/neje_oracle/plotter_daemon.py` — 1 ошибка (PlotterDaemon constructor arg)
- `src/neje_oracle/svg_gcode.py` — 3 ошибки (object assignment)

## Проблема в gui_service.py
`GUI_DEFAULTS` — это dict[str, dict[str, object]] (смешанные типы). При обращении `GUI_DEFAULTS['section']['key']` mypy считает, что значение имеет тип `object`, что вызывает ошибки при передаче в `float()`, `number_control()`, `calibration_slider_row()` и присваивании в переменные с типом `float`, `bool`, `str`, `int`.

### Решение для gui_service.py — ТОП-5 по частоте:

1. **Argument 1 to "float" has incompatible type "object"** (37 случаев)
   - Везде, где выполняется `float(x)` и x приходит из GUI_DEFAULTS
   - Добавить явное приведение: `float(GUI_DEFAULTS['section']['key'])` → работает, но mypy всё равно ругается
   - Правильно: создать вспомогательную функцию-аксессор `_get_float(key: str, section: str) -> float` которая берёт значение из GUI_DEFAULTS и явно приводит к float, либо использовать `cast(float, ...)`
   - Лучше всего: вместо `float(GUI_DEFAULTS[...][...])` использовать `GUI_FLOAT_DEFAULTS[section][key]` — параллельный typing.Dict[str, float]

2. **Argument "default" to "number_control" / "calibration_slider_row" has incompatible type "object"; expected "float"**
   - То же самое: добавить явное приведение: `default=cast(float, GUI_DEFAULTS[...][...])`
   - Или изменить сигнатуру функций `number_control` и `calibration_slider_row` принимать `object | float`

3. **Incompatible types in assignment (expression has type "object", variable has type "float|bool|str|int")**
   - Исправить так же через `cast()` или `float()` | `str()` | `bool()` обёртки

### Решения для остальных файлов:

4. **src/neje_oracle/config.py** — return value type mismatch
   - Найти функцию, которая возвращает `object` вместо ожидаемого типа, добавить explicit return type annotation

5. **src/neje_oracle/session_uploader.py** — optional float conversion
   - Исправить: `float(x or 0.0)` или `float(x) if x is not None else 0.0`

6. **src/neje_oracle/transport.py** — tuple narrowing
   - `tuple[float, ...] | None` нельзя присвоить в `tuple[float, float, float] | None`
   - Исправить: добавить `assert result is not None and len(result) == 3` или cast

7. **src/neje_oracle/firebase_io.py** — assignment type
   - Исправить: добавить explicit type annotation при присваивании

8. **src/neje_oracle/plotter_daemon.py** — PlotterDaemon constructor arg type
   - Аргумент имеет тип `FirebaseRemoteRepository | _LocalOnlyPlotterRemote`, а ожидается `FirebaseRemoteRepository`
   - Добавить Protocol `PlotterRemote` с методами `claim_next_plot_job`, `update_plot_job`, `download_asset`
   - Изменить сигнатуру конструктора на `PlotterRemote`

9. **src/neje_oracle/svg_gcode.py** — object assignments (3 места)
   - Добавить explicit type annotations или cast

## Текущий статус mypy
```
Found 65 errors in 9 files (checked 26 source files)
```

## After creating
Не запускай тесты. Просто исправь ошибки типов и напиши "Mypy fixes applied."

## Примечания
- Не трогай ошибки `import-untyped` (svgpathtools, firebase_admin, qrcode) — они уже suppressed в mypy config
- Сохрани существующее поведение кода, только исправь типы
- Везде, где возможно, используй минимальные изменения с `cast()` вместо переписывания большой логики
