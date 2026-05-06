---
name: svg-normalization
version: 1.0
category: core
tags: [svg, normalization, processing]
dependencies: []
---

# Навык: Нормализация SVG

## Описание
Нормализация SVG для совместимости с NejePlotter и G-code генерацией.

## Ключевые компоненты

### 1. `svg_normalizer.py`
Основной модуль нормализации SVG.

### 2. `firebase_svg_normalizer.py`
Специальная версия для Firebase интеграции.

### 3. Процесс нормализации
1. Загрузка SVG
2. Очистка от лишних элементов
3. Преобразование координат
4. Упрощение путей
5. Конвертация в внутренний формат

## Использование

### Базовый вызов
```python
from neje_oracle.svg_normalizer import SVGNormalizer

normalizer = SVGNormalizer(config)
normalized_svg = normalizer.normalize(svg_content)
```

### С Firebase
```python
from neje_oracle.firebase_svg_normalizer import FirebaseSVGNormalizer

normalizer = FirebaseSVGNormalizer(firebase_config)
normalized_svg = normalizer.normalize_for_firebase(svg_content)
```

## Параметры конфигурации
- DPI: 72 (по умолчанию)
- Масштаб: 1.0
- Точность: 0.1mm
- Минимальный путь: 0.5mm

## Ошибки и обработка
- `SVGParseError` - ошибка парсинга
- `NormalizationError` - ошибка нормализации
- `ValidationError` - ошибка валидации

## Мониторинг
- Логирование в `logs/svg_normalization.log`
- Метрики в `pulse_logger.py`
- Уведомления через Hermes

## Примеры
```svg
<!-- До нормализации -->
<svg viewBox="0 0 100 100">...</svg>

<!-- После нормализации -->
<svg viewBox="0 0 720 720" xmlns="http://www.w3.org/2000/svg">...</svg>
```

## Связанные навыки
- [[gcode-generation]] - Генерация G-code
- [[plotter-control]] - Управление плоттером
- [[session-management]] - Управление сессиями