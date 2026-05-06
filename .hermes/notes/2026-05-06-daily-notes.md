# Daily Notes - 2026-05-06

## Сегодняшние наблюдения

### Архитектура проекта
- Проект использует модульную структуру с пакетом `neje_oracle`
- Ключевые сервисы: Plotter, Uploader, GUI, Firebase
- Наличие демона (`plotter_daemon.py`) и агентов (`uploader_agent_service.py`)
- Сложная система нормализации SVG

### Интересные находки
- 224 директории с сырыми сессиями в `sessions_raw/`
- 80+ директорий с обработанными сессиями в `assets/sessions/`
- Интеграция с Firebase для облачного хранения
- Flutter приложение на GitHub Pages для отображения результатов

### Технические детали
- Используется Poetry/UV для управления зависимостями
- Тесты покрывают ключевые модули
- Наличие системы дизайна в `assets/Design system/`
- Подробная документация и планы

## Вопросы и идеи

### Вопросы
- [[Как работает нормализация SVG?]]
- [[Как конвертируется SVG в G-code?]]
- [[Какие модели данных используются?]]
- [[Как настроена интеграция с Firebase?]]

### Идеи
- [[Интеграция с Hermes Agent для умных уведомлений]]
- [[Автоматизация обработки сессий]]
- [[Улучшение системы нормализации SVG]]
- [[Создание публичной галереи с фильтрами]]

## Задачи на завтра
- [ ] Изучить `svg_normalizer.py`
- [ ] Понять `svg_gcode.py`
- [ ] Посмотреть `firebase_svg_normalizer.py`
- [ ] Запустить тесты

## Теги
#архитектура #интеграция #firebase #svg #gcode #plotter

## Ссылки
- Исходный код: `/Users/berloga/Documents/GitHub/NejeDraw/src/`
- Документация: `/Users/berloga/Documents/GitHub/NejeDraw/docs/`
- Планы: `/Users/berloga/Documents/GitHub/NejeDraw/.hermes/plans/`
- Карты: `/Users/berloga/Documents/GitHub/NejeDraw/.hermes/maps/`
- Логи: `/Users/berloga/Documents/GitHub/NejeDraw/logs/`
- Сессии: `/Users/berloga/Documents/GitHub/NejeDraw/sessions_raw/`

## Прогресс
- [x] Создал карту проекта
- [x] Настроил систему планирования
- [ ] Изучить ключевые модули
- [ ] Запустить тесты
- [ ] Интегрироваться с Hermes