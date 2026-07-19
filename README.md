# AVTO-hub — личный кабинет

Личный кабинет клиента и панель менеджера для компании по импорту автомобилей.

- **Кабинет клиента**: купленные авто и статусы доставки, договора с электронной подписью, оплаты (депозит / оплата за авто / возврат), баланс.
- **Панель менеджера**: клиенты, авто и статусы, документы, баланс, курсы валют.

## Стек

- Бэкенд: FastAPI, SQLAlchemy (async), PostgreSQL
- Фронтенд: HTML/CSS/JS (без сборки)
- Электронная подпись: Podpislon
- Письма: SMTP
- Запуск: Docker Compose + nginx

## Структура

```
backend/            серверная часть (FastAPI)
frontend/           кабинет клиента и панель менеджера
nginx/              конфигурация nginx
docker-compose.yml  сборка: PostgreSQL + бэкенд + nginx
.env.example        шаблон переменных окружения
```

## Развёртывание (Docker)

1. Установить Docker и Docker Compose.
2. Скопировать `.env.example` в `.env` и заполнить значения (см. ниже).
3. Запустить:

   ```
   docker compose up -d --build
   ```

4. Привязать поддомен к серверу и настроить HTTPS (nginx-конфиг в `nginx/`).
5. В личном кабинете Podpislon указать адрес уведомлений (webhook):
   `https://<поддомен>/api/webhooks/podpislon`


## Локальная разработка (без Docker)

```
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # заполнить SECRET_KEY, оставить SQLite в DATABASE_URL
uvicorn app.main:app --reload
```

Фронтенд (`frontend/cabinet.html`, `frontend/admin.html`) открывается в браузере
и обращается к локальному бэкенду.
