#!/usr/bin/env bash
set -euo pipefail

db_user="${TRINITY_DB_USER:-trinity}"
db_password="${TRINITY_DB_PASSWORD:-trinity}"

mysql=(mysql -uroot -p"${MARIADB_ROOT_PASSWORD}")

"${mysql[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS world DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS characters DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS auth DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS hotfixes DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS '${db_user}'@'%' IDENTIFIED BY '${db_password}';
GRANT ALL PRIVILEGES ON world.* TO '${db_user}'@'%';
GRANT ALL PRIVILEGES ON characters.* TO '${db_user}'@'%';
GRANT ALL PRIVILEGES ON auth.* TO '${db_user}'@'%';
GRANT ALL PRIVILEGES ON hotfixes.* TO '${db_user}'@'%';
FLUSH PRIVILEGES;
SQL

"${mysql[@]}" auth < /trinity/sql/base/auth_database.sql
"${mysql[@]}" characters < /trinity/sql/base/characters_database.sql
"${mysql[@]}" world < /trinity/sql/base/dev/world_database.sql
"${mysql[@]}" hotfixes < /trinity/sql/base/dev/hotfixes_database.sql
