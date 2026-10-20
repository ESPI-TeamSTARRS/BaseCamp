#!/bin/sh
# Cree le role et la base propres a shop (premier demarrage du volume uniquement).
# Le compte administrateur n'est jamais utilise par les services.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v shop_user="$SHOP_DB_USER" -v shop_password="$SHOP_DB_PASSWORD" -v shop_db="$SHOP_DB_NAME" <<'SQL'
CREATE ROLE :"shop_user" LOGIN PASSWORD :'shop_password';
CREATE DATABASE :"shop_db" OWNER :"shop_user";
REVOKE ALL ON DATABASE :"shop_db" FROM PUBLIC;
SQL
