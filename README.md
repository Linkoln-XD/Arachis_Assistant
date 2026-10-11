# Arachis Assistant

Сервер личного календаря: задачи, встречи и напоминания. Контракт HTTP лежит в `docs/API-контракт.docx`.

## Локальный запуск

Нужен Docker.

```bash
docker compose up --build -d
```

Сервис слушает http://127.0.0.1:8000. Базовый путь API — `/api/v1`. Проверка: http://127.0.0.1:8000/api/v1/health отвечает `{"status":"ok"}`.

Авторизация — заголовок `Authorization: Bearer <access_token>`. Токен выдают `POST /api/v1/auth/register` и `POST /api/v1/auth/login`. Сервер не использует cookie.

Браузерный клиент на `http://localhost:5173` или `http://127.0.0.1:5173` может обращаться к API. Другой адрес задаётся переменной `CORS_ORIGINS` (образец — `.env.example`). Разрешены заголовки `Authorization`, `Content-Type` и `Idempotency-Key`. Скрипт может прочитать заголовок ответа `Location`.

Остановить сервис: `docker compose down`.
