---
name: uploader-service
version: 1.0
category: core
tags: [uploader, firebase, api]
dependencies: []
---

# Навык: Сервис загрузки

## Описание
Сервис загрузки результатов на Firebase и публичную галерею.

## Ключевые компоненты

### 1. `uploader_service.py`
Основной сервис загрузки.

### 2. `uploader_agent_service.py`
Агент загрузки (фоновый).

### 3. `session_uploader.py`
Загрузчик сессий.

## Архитектура

### Основной сервис
- REST API или CLI интерфейс
- Обработка очереди загрузок
- Валидация данных
- Обработка ошибок

### Агент загрузки
- Фоновый процесс
- Мониторинг новых сессий
- Автоматическая загрузка
- Повтор при ошибках

## Загрузка на Firebase

### Realtime Database
```python
from neje_oracle.uploader_service import UploaderService

uploader = UploaderService(firebase_config)
uploader.upload_to_database(session_data)
```

### Cloud Storage
```python
uploader.upload_to_storage(
    session_id=session.id,
    file_path=gcode_file,
    file_type="gcode"
)
```

### Аутентификация
- Email/пароль
- Google OAuth
- Анонимный доступ
- Пользовательские токены

## Публичная галерея

### Создание записи
```python
uploader.publish_to_gallery(
    session_id=session.id,
    title="My Artwork",
    description="Description of my artwork",
    tags=["abstract", "black&white"]
)
```

### Галерея на GitHub Pages
- Статический сайт
- Фильтры по тегам
- Поиск
- Пагинация
- Лайки/комментарии

## Очередь загрузок

### Управление очередью
- Приоритизация
- Ограничение скорости
- Повтор при ошибках
- Мониторинг

### Формат очереди
```json
{
  "queue_id": "queue_123",
  "items": [
    {"session_id": "session_1", "priority": 1, "retries": 0},
    {"session_id": "session_2", "priority": 2, "retries": 1}
  ],
  "status": "processing",
  "created_at": "2026-05-06T10:00:00Z"
}
```

## Мониторинг

### Метрики
- Количество загрузок
- Размер данных
- Время загрузки
- Ошибки
- Пропускная способность

### Логирование
- `logs/uploader_service.log`
- `logs/uploader_agent.log`
- `pulse_logger.py` метрики

## Уведомления
- Hermes Notification System
- Telegram при завершении
- Email при ошибках
- Логи в `logs/`

## Безопасность

### Проверка данных
- Валидация форматов
- Проверка размера файлов
- Антивирусная проверка
- Ручная модерация (опционально)

### Контроль доступа
- ACL для пользователей
- Приватные/публичные сессии
- Редактирование/удаление
- Аудит действий

## Производительность

### Оптимизации
- Параллельные загрузки
- Сжатие данных
- Кэширование
- Балансировка нагрузки

### Масштабирование
- Горизонтальное масштабирование
- Балансировщик нагрузки
- CDN для статики
- Шардирование базы данных

## Связанные навыки
- [[session-management]] - Управление сессиями
- [[firebase-io]] - Интеграция с Firebase
- [[plotter-control]] - Управление плоттером
- [[gcode-generation]] - Генерация G-code