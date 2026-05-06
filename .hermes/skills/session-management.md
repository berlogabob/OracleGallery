---
name: session-management
version: 1.0
category: core
tags: [sessions, storage, firebase]
dependencies: []
---

# Навык: Управление сессиями

## Описание
Создание, хранение и управление сессиями пользователя.

## Ключевые компоненты

### 1. `session_generator.py`
Генератор сессий.

### 2. `session_uploader.py`
Загрузчик сессий.

### 3. `store.py`
Хранилище данных.

## Структура сессии

### Формат данных
```json
{
  "id": "session_123",
  "user_id": "user_456",
  "created_at": "2026-05-06T10:00:00Z",
  "svg_content": "normalized_svg_data",
  "gcode_content": "gcode_data",
  "settings": {
    "speed": 800,
    "power": 100,
    "passes": 1,
    "depth": 0.1
  },
  "preview_image": "base64_image",
  "status": "completed",
  "metadata": {
    "pages": 1,
    "complexity": "medium",
    "duration": 120
  }
}
```

## Workflow сессии

### 1. Создание
```python
from neje_oracle.session_generator import SessionGenerator

generator = SessionGenerator(config)
session = generator.create_session(
    svg_content=svg_data,
    settings=settings
)
```

### 2. Обработка
```python
# Нормализация SVG
normalized = svg_normalizer.normalize(svg_data)

# Генерация G-code
gcode = svg_gcode.convert(normalized)

# Сохранение сессии
store.save_session(session)
```

### 3. Загрузка
```python
# Локальная загрузка
session_data = store.get_session(session_id)

# Firebase загрузка
uploader = SessionUploader(firebase_config)
uploader.upload_session(session)
```

## Хранение

### Локальное хранение
- `sessions_raw/` - Сырые сессии
- `sessions/` (в assets) - Обработанные сессии
- `spool/` - Очередь заданий

### Firebase хранение
- Realtime Database
- Cloud Storage
- Authentication

## Статусы сессии

### Возможные статусы
- `pending` - В ожидании
- `processing` - В обработке
- `completed` - Завершена
- `error` - Ошибка
- `uploading` - Загрузка
- `uploaded` - Загружена

## Мониторинг

### Метрики
- Количество сессий
- Статусы сессий
- Время обработки
- Размер файлов

### Логирование
- `logs/session_generator.log`
- `logs/session_uploader.log`
- `pulse_logger.py` метрики

## Уведомления
- Hermes Notification System
- Telegram
- Email при ошибках
- Логи в `logs/`

## Безопасность
- Аутентификация Firebase
- Проверка прав доступа
- Шифрование данных
- Резервное копирование

## Связанные навыки
- [[svg-normalization]] - Нормализация SVG
- [[gcode-generation]] - Генерация G-code
- [[plotter-control]] - Управление плоттером
- [[uploader-service]] - Сервис загрузки
- [[firebase-io]] - Интеграция с Firebase