#!/bin/sh
# Cree le role de supervision `monitoring` sur l'instance Postgres de shop (lecture seule).
# Execute par l'image au premier demarrage du volume uniquement ; sur une base existante, voir
# docs/deployment/supervision.md. Idempotent : peut etre rejoue sans risque.
# Le role n'a aucun droit sur les donnees : pg_monitor donne les statistiques, pas les tables,
# et CONNECT sur la base applicative est retire a PUBLIC (init-shop-db.sh).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v monitoring_password="$MONITORING_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE monitoring LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring') \gexec
ALTER ROLE monitoring WITH LOGIN PASSWORD :'monitoring_password' CONNECTION LIMIT 5;
GRANT pg_monitor TO monitoring;
ALTER ROLE monitoring SET default_transaction_read_only = on;
SQL
