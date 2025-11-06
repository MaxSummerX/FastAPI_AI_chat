#!/bin/bash
set -e

# Используем heredoc для выполнения SQL с переменными окружения
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Создаем пользователя для auth сервиса
    CREATE USER "$DB_USER" WITH ENCRYPTED PASSWORD '$DB_PASSWORD' LOGIN;

    -- Создаем базу данных для auth сервиса
    CREATE DATABASE "$DB_NAME" OWNER "$DB_USER";
EOSQL

# Подключаемся к созданной БД и выдаем права
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB_NAME" <<-EOSQL
    -- Даем права на схему public
    GRANT ALL ON SCHEMA public TO "$DB_USER";

    -- Даем права на создание таблиц
    GRANT CREATE ON SCHEMA public TO "$DB_USER";

    -- Даем права на все существующие таблицы
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "$DB_USER";

    -- Даем права на все будущие таблицы
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "$DB_USER";

    -- Даем права на все последовательности
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "$DB_USER";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "$DB_USER";
EOSQL

echo "Database $DB_NAME and user $DB_USER created successfully"
