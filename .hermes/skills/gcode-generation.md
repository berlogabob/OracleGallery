---
name: gcode-generation
version: 1.0
category: core
tags: [gcode, svg, conversion]
dependencies: []
---

# Навык: Генерация G-code

## Описание
Конвертация нормализованного SVG в G-code для NejePlotter.

## Ключевые компоненты

### 1. `svg_gcode.py`
Основной модуль конвертации SVG → G-code.

### 2. Алгоритм генерации
1. Парсинг SVG путей
2. Преобразование в команды движения
3. Добавление скоростных параметров
4. Генерация G-code файла

## Использование

### Базовый вызов
```python
from neje_oracle.svg_gcode import SVGToGCode

converter = SVGToGCode(config)
gcode = converter.convert(normalized_svg)
```

### С параметрами
```python
gcode = converter.convert(
    normalized_svg,
    speed=800,
    power=100,
    passes=1,
    depth=0.1
)
```

## Формат G-code

### Команды
- `G21` - Миллиметры
- `G90` - Абсолютное позиционирование
- `G0` - Быстрое перемещение
- `G1` - Рабочее перемещение
- `M3` - Включение лазера
- `M5` - Выключение лазера
- `G4` - Пауза

### Пример
```
G21 G90
G0 X0 Y0
M3 S100
G1 X10 Y10 F800
G1 X20 Y10
G1 X20 Y20
G1 X10 Y20
G1 X10 Y10
M5
G0 X0 Y0
```

## Конфигурация

### Скорости
- `travel_speed`: 3000 mm/min
- `work_speed`: 800 mm/min
- `laser_on_delay`: 100 ms
- `laser_off_delay`: 100 ms

### Мощность
- `laser_power`: 100% (макс)
- `min_laser_power`: 0%
- `max_laser_power`: 100%

## Ошибки и обработка
- `GCodeGenerationError` - ошибка генерации
- `PathProcessingError` - ошибка обработки пути
- `ConfigurationError` - ошибка конфигурации

## Мониторинг
- Логирование в `logs/gcode_generation.log`
- Метрики в `pulse_logger.py`
- Уведомления через Hermes

## Производительность
- 1 страница A4: ~2 секунды
- 10 страниц: ~15 секунд
- Зависит от сложности SVG

## Связанные навыки
- [[svg-normalization]] - Нормализация SVG
- [[plotter-control]] - Управление плоттером
- [[session-management]] - Управление сессиями