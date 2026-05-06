# Диаграмма компонентов NejeDraw

```
+-----------------------------------------------------------------------+
|                         NejeDraw Application                          |
+-----------------------------------------------------------------------+
                            |  |  |
         .--------------------' |  '--------------------.
         |                       |                       |
+-------v------+       +--------v--------+       +------v-------+
|  GUI Layer   |       |  Business Logic |       |  Data Layer  |
| (GUI Service)|       | (Plotter,      |       | (Store,      |
|              |       |   Uploader,    |       |  SessionMgr) |
| +-----------+|       |   SessionGen)  |       |              |
| |  GUI UI   ||       +--------+--------+       +--------------+
| |  Modes   ||                |                 
| +-----------+|                |                 
+--------------+                |                 
         ^                      v                 
         |           +----------+----------+      
         |           |   Core Services      |      
         |           | (SVG Normalizer,    |      
         |           |  G-code Gen,        |      
         |           |  Firebase IO)       |      
         |           +----------+----------+      
         |                      |                 
    .----+----.           .----+----.           
    |  User   |           |  Hardware  |       
    | (Plotter|           | (NejePlotter)|     
    |  GUI)   |           |            |       
    '---------'           '------------'       
                                             
```

## Поток данных

### Основной workflow
```
1. User Input (SVG) 
   → GUI Layer 
   → SessionGenerator 
   → SessionManager 
   → SVGNormalizer 
   → SVGToGCode 
   → PlotterService 
   → PlotterDaemon 
   → Hardware

2. User Input (GUI)
   → GUI Service
   → Business Logic
   → Data Layer
   → FirebaseIO
   → Cloud Storage
```

## Модули и их взаимодействие

### Модуль SVGNormalizer
```
SVGNormalizer
    │
    ├── load(svg_content)
    ├── clean()        → Удаление лишних элементов
    ├── transform()    → Изменение координат
    ├── simplify()     → Упрощение путей
    ├── validate()     → Проверка корректности
    └── save()         → Сохранение результата
```

### Модуль SVGToGCode
```
SVGToGCode
    │
    ├── parse_paths()   → Парсинг SVG путей
    ├── convert()       → Конвертация в команды
    ├── add_speed()     → Добавление скоростей
    ├── optimize()      → Оптимизация G-code
    └── generate()      → Генерация G-code файла
```

### Модуль PlotterDaemon
```
PlotterDaemon
    │
    ├── connect()       → Подключение к плоттеру
    ├── disconnect()    → Отключение
    ├── send_command()  → Отправка команд
    ├── read_response() → Чтение ответа
    ├── monitor()       → Мониторинг состояния
    └── handle_error()  → Обработка ошибок
```

## Технологические слои

### Presentation Layer (GUI)
- PyQt/PySide (GUI UI)
- REST API (для мобильного приложения)
- CLI интерфейс

### Business Logic Layer
- SVGNormalizer
- SVGToGCode
- PlotterService
- SessionManager
- UploaderService

### Data Access Layer
- Store (локальное хранилище)
- FirebaseIO (облачное хранилище)
- SessionUploader (загрузчик сессий)

### Infrastructure Layer
- PlotterDaemon (демон плоттера)
- UploaderAgent (агент загрузки)
- PulseLogger (мониторинг)
- Supervisor (супервизор процессов)

## Потоки данных

### Создание сессии
```
User → GUI → SessionGenerator → Store → SessionManager → SVGNormalizer → SVGToGCode → PlotterService → PlotterDaemon → Hardware
```

### Загрузка сессии
```
SessionManager → SessionUploader → FirebaseIO → Cloud Storage → Public Gallery
```

### Мониторинг
```
PulseLogger → Supervisor → Log Files → Hermes Notifications
```

## Зависимости между модулями

### Прямые зависимости
- `SVGNormalizer` → `config.py`, `models.py`
- `SVGToGCode` → `SVGNormalizer`, `config.py`
- `PlotterService` → `PlotterDaemon`, `config.py`
- `SessionManager` → `Store`, `SessionGenerator`, `SVGNormalizer`, `SVGToGCode`
- `UploaderService` → `FirebaseIO`, `SessionManager`

### Косвенные зависимости
- Все модули → `models.py` (общие модели)
- Все модули → `oracle_logging.py` (логирование)
- GUI модули → `gui_modes.py`, `layout.py`

## Масштабируемость

### Горизонтальное масштабирование
- Несколько экземпляров PlotterDaemon
- Балансировщик нагрузки
- Шардирование сессий

### Вертикальное масштабирование
- Увеличение мощности железа
- Оптимизация алгоритмов
- Кэширование промежуточных результатов

## Отказоустойчивость

### Резервирование
- Дублирование демона плоттера
- Резервные каналы связи
- Автоматическое восстановление
- Резервное копирование сессий

### Мониторинг
- Пульс-логгер
- Автоматические проверки
- Уведомления об ошибках
- Логирование всех действий

## Безопасность

### Уровни доступа
- Администратор: полный доступ
- Пользователь: создание сессий, просмотр галереи
- Гость: только просмотр

### Защита данных
- Шифрование при передаче
- Шифрование при хранении
- Резервное копирование
- Антивирусная проверка

## Производительность

### Ключевые метрики
- Время нормализации SVG: 0.5-2 секунды
- Время генерации G-code: 1-5 секунд
- Время обработки сессии: 2-10 секунд
- Время загрузки: зависит от размера файла

### Оптимизации
- Параллельная обработка
- Кэширование результатов
- Оптимизация алгоритмов
- Использование асинхронных операций