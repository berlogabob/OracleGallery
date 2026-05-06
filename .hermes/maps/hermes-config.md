# Конфигурация Hermes Agent для NejeDraw проекта

## Основные настройки

### Провайдеры моделей
```yaml
models:
  default: claude-sonnet-4
  fallback: claude-haiku-4
  specialized:
    - name: code-interpreter
      model: claude-sonnet-4
    - name: research
      model: claude-sonnet-4
```

### Интеграции
```yaml
integrations:
  hermes-notifications:
    enabled: true
    channels:
      - telegram
      - email
      - logs
  firebase:
    enabled: true
    config_path: .env.firebase
  github:
    enabled: true
    repo: berloga/NejeDraw
```

### Уведомления
```yaml
notifications:
  telegram:
    chat_id: "-1001234567890"
    api_token: "your_telegram_bot_token"
  email:
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    sender: "hermes@nejedraw.com"
    recipients: ["user@example.com"]
  log_level: "INFO"
```

## Настройки проекта

### Рабочая директория
```yaml
project:
  root: "/Users/berloga/Documents/GitHub/NejeDraw"
  src: "src/neje_oracle"
  assets: "assets"
  sessions: "sessions_raw"
  logs: "logs"
  scripts: "scripts"
```

### Переменные окружения
```yaml
env:
  OLLAMA_URL: "http://localhost:11434"
  PLOTTER_PORT: "/dev/tty.usbmodem14201"
  FIREBASE_CONFIG: ".env.firebase"
  PLOTTER_DPI: "72"
  MAX_SESSIONS: "1000"
```

## Настройки навыков

### SVG нормализация
```yaml
skills:
  svg-normalization:
    enabled: true
    config:
      dpi: 72
      scale: 1.0
      precision: 0.1
      min_path_length: 0.5
```

### G-code генерация
```yaml
  gcode-generation:
    enabled: true
    config:
      travel_speed: 3000
      work_speed: 800
      laser_power: 100
      laser_on_delay: 100
      laser_off_delay: 100
```

### Управление плоттером
```yaml
  plotter-control:
    enabled: true
    config:
      port: "/dev/tty.usbmodem14201"
      baudrate: 115200
      timeout: 30
      retries: 3
```

### Управление сессиями
```yaml
  session-management:
    enabled: true
    config:
      max_sessions: 1000
      session_ttl: 2592000  # 30 дней
      firebase_sync: true
      auto_publish: false
```

### Сервис загрузки
```yaml
  uploader-service:
    enabled: true
    config:
      max_concurrent_uploads: 5
      retry_attempts: 3
      batch_size: 10
      gallery_publish: true
```

## Мониторинг и логирование

### Логи
```yaml
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  handlers:
    - type: "file"
      path: "logs/hermes.log"
      max_size: 10485760  # 10MB
      backup_count: 5
    - type: "telegram"
      chat_id: "-1001234567890"
      level: "ERROR"
    - type: "console"
      level: "INFO"
```

### Пульс-логгер
```yaml
pulse_logger:
  enabled: true
  interval: 60  # секунд
  metrics:
    - "active_sessions"
    - "plotter_status"
    - "upload_queue"
    - "system_load"
  alerts:
    - "high_load"
    - "plotter_error"
    - "no_activity"
```

## Безопасность

### Аутентификация
```yaml
security:
  firebase:
    enabled: true
    api_key: "${FIREBASE_API_KEY}"
    auth_domain: "${FIREBASE_AUTH_DOMAIN}"
    project_id: "${FIREBASE_PROJECT_ID}"
    storage_bucket: "${FIREBASE_STORAGE_BUCKET}"
    messaging_sender_id: "${FIREBASE_MESSAGING_SENDER_ID}"
    app_id: "${FIREBASE_APP_ID}"
```

### API ключи
```yaml
  api_keys:
    - name: "ollama"
      value: "${OLLAMA_API_KEY}"
    - name: "github"
      value: "${GITHUB_API_TOKEN}"
    - name: "telegram"
      value: "${TELEGRAM_BOT_TOKEN}"
```

## Резервное копирование

### Автобэкап
```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"  # Каждый день в 2 AM
  paths:
    - "/Users/berloga/Documents/GitHub/NejeDraw/assets/sessions"
    - "/Users/berloga/Documents/GitHub/NejeDraw/src"
    - "/Users/berloga/Documents/GitHub/NejeDraw/.hermes"
  destination: "/Volumes/Backup/NejeDraw"
  retention: 30  # дней
```

## CI/CD

### GitHub Actions
```yaml
ci_cd:
  enabled: true
  workflows:
    - name: "tests"
      schedule: "0 4 * * *"  # Каждый день в 4 AM
      branches: ["main", "develop"]
    - name: "deploy"
      events: ["push", "pull_request"]
      environment: "production"
```

## Документация

### Автодокументация
```yaml
docs:
  enabled: true
  source: "src/neje_oracle"
  output: "docs/api"
  format: "sphinx"
  schedule: "0 1 * * *"  # Каждый день в 1 AM
```

## Тестирование

### Автотесты
```yaml
testing:
  enabled: true
  schedule: "0 3 * * *"  # Каждый день в 3 AM
  coverage_threshold: 80%
  report_email: "team@nejedraw.com"
```

## Планирование

### Cron задания
```yaml
cron:
  cleanup:
    schedule: "0 0 * * *"  # Каждый день в 00:00
    command: "python scripts/cleanup_old_sessions.py"
  analytics:
    schedule: "0 5 * * *"  # Каждый день в 5 AM
    command: "python scripts/generate_analytics.py"
  backup:
    schedule: "0 2 * * *"  # Каждый день в 2 AM
    command: "python scripts/backup_data.py"
```

## Производительность

### Мониторинг
```yaml
performance:
  enabled: true
  metrics:
    - "response_time"
    - "throughput"
    - "error_rate"
    - "memory_usage"
    - "cpu_usage"
  alerts:
    - "high_response_time"
    - "high_error_rate"
    - "low_memory"
    - "high_cpu"
```

## Уведомления

### Каналы
```yaml
alerts:
  channels:
    - "telegram"
    - "email"
    - "slack"
    - "sms"
  thresholds:
    - "response_time>5s"
    - "error_rate>5%"
    - "memory_usage>80%"
    - "plotter_error"
```

## Ссылки
- Исходный код: `/Users/berloga/Documents/GitHub/NejeDraw/src/`
- Документация: `/Users/berloga/Documents/GitHub/NejeDraw/docs/`
- Конфигурация: `/Users/berloga/Documents/GitHub/NejeDraw/.hermes/maps/`
- Планы: `/Users/berloga/Documents/GitHub/NejeDraw/.hermes/plans/`
- Логи: `/Users/berloga/Documents/GitHub/NejeDraw/logs/`
- Сессии: `/Users/berloga/Documents/GitHub/NejeDraw/sessions_raw/`