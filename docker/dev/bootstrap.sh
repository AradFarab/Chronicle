#!/usr/bin/env bash
# Idempotent dev bootstrap. Run inside the `frappe` container (user: frappe):
#
#   docker compose -f docker/dev/compose.yml exec frappe bash /workspace/hozur/docker/dev/bootstrap.sh
#
# Creates a Frappe version-16 bench in the `bench` volume, points it at the compose
# MariaDB/Redis services, soft-links this repository as apps/hozur, creates the dev
# site and installs hozur on it. Safe to re-run.
set -euo pipefail

BENCH_DIR=/home/frappe/frappe-bench
APP_SRC=/workspace/hozur
SITE="${SITE:-hozur.localhost}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-123}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# Named volumes are created root-owned.
sudo chown frappe:frappe "$BENCH_DIR"

if [ ! -d "$BENCH_DIR/apps/frappe" ]; then
	log "bench init (frappe $FRAPPE_BRANCH)"
	bench init --ignore-exist --skip-redis-config-generation --dev \
		--frappe-branch "$FRAPPE_BRANCH" "$BENCH_DIR"
fi
cd "$BENCH_DIR"

log "Pointing bench at compose services"
bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
bench set-config -g developer_mode 1 --parse
# Redis runs in its own containers, so honcho must not start it.
sed -i '/^redis/d' Procfile

if [ -f "$APP_SRC/pyproject.toml" ] && [ ! -e apps/hozur ]; then
	log "Linking $APP_SRC as apps/hozur"
	bench get-app --soft-link "$APP_SRC"
fi

if [ ! -d "sites/$SITE" ]; then
	log "Creating site $SITE"
	bench new-site "$SITE" \
		--db-root-username root \
		--db-root-password "$DB_ROOT_PASSWORD" \
		--admin-password "$ADMIN_PASSWORD" \
		--mariadb-user-host-login-scope=%
fi
bench --site "$SITE" set-config developer_mode 1 --parse
bench use "$SITE"

if [ -e apps/hozur ] && ! bench --site "$SITE" list-apps | grep -q '^hozur'; then
	log "Installing hozur on $SITE"
	bench --site "$SITE" install-app hozur
fi

log "Done. Start the dev server with:  bench start   ->  http://$SITE:8000  (Administrator / $ADMIN_PASSWORD)"
