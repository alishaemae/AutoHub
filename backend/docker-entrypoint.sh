#!/bin/sh
set -e

# Ждём БД (PostgreSQL) и применяем миграции
echo "Применяю миграции Alembic..."
alembic upgrade head

echo "Запуск сервера..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
