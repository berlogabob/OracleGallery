---
name: plotter-control
version: 1.0
category: core
tags: [plotter, daemon, hardware]
dependencies: []
---

# Навык: Управление плоттером

## Описание
Управление NejePlotter через демона и сервисы.

## Ключевые компоненты

### 1. `plotter_daemon.py`
Демон управления плоттером.

### 2. `plotter_service.py`
Сервис взаимодействия с плоттером.

### 3. `supervisor.py`
Супервизор процессов.

## Архитектура

### Демон плоттера
- Фоновый процесс
- Управление через сокеты
- Мониторинг состояния
- Обработка ошибок

### Коммуникация
```
GUI/CLI → Supervisor → Plotter Daemon → Plotter Hardware
```

## Запуск демона

### Через скрипт
```bash
./start_plotter_daemon.sh
```

### Через Python
```python
from neje_oracle.plotter_daemon import PlotterDaemon

daemon = PlotterDaemon(config)
daemon.start()
```

## Команды плоттеру

### Основные команды
- `connect` - Подключение к плоттеру
- `disconnect` - Отключение
- `home` - Возврат в нулевую позицию
- `move` - Перемещение
- `laser_on` - Включение лазера
- `laser_off` - Выключение лазера
- `pause` - Пауза
- `resume` - Возобновление
- `stop` - Стоп
- `status` - Статус

### Пример
```python
daemon.send_command("connect /dev/tty.usbmodem14201")
daemon.send_command("home")
daemon.send_command("laser_on")
daemon.send_command("move X10 Y10")
daemon.send_command("laser_off")
```

## Мониторинг состояния

### Метрики
- `is_connected` - Подключен
- `is_homed` - Нулевая позиция
- `status` - Текущий статус
- `error` - Ошибка
- `progress` - Прогресс

### Логирование
- `logs/plotter_daemon.log`
- `logs/plotter_service.log`
- `pulse_logger.py` метрики

## Обработка ошибок

### Типы ошибок
- `ConnectionError` - Ошибка подключения
- `CommunicationError` - Ошибка связи
- `HardwareError` - Ошибка железа
- `CommandError` - Ошибка команды

### Восстановление
- Автоматическое переподключение
- Повторение команд
- Пауза при ошибках
- Уведомления

## Уведомления
- Hermes Notification System
- Telegram
- Email
- Логи в `logs/`

## Безопасность
- Проверка подключения перед командами
- Таймауты команд
- Валидация параметров
- Резервные каналы связи

## Связанные навыки
- [[svg-normalization]] - Нормализация SVG
- [[gcode-generation]] - Генерация G-code
- [[session-management]] - Управление сессиями
- [[uploader-service]] - Сервис загрузки