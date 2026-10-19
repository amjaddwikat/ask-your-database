#!/bin/bash
# Two least-privilege users:
#  - the agents' warehouse user can only SELECT from telecom_dw
#  - the app user owns the `app` schema (conversation memory) and nothing else
set -euo pipefail

mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS 'warehouse_ro'@'%' IDENTIFIED BY '${WAREHOUSE_DB_PASSWORD}';
GRANT SELECT ON telecom_dw.* TO 'warehouse_ro'@'%';

CREATE USER IF NOT EXISTS 'app'@'%' IDENTIFIED BY '${APP_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON app.* TO 'app'@'%';

FLUSH PRIVILEGES;
SQL
