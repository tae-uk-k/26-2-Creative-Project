#!/bin/sh
# 새 빈 DB에만 복구한다. 운영 DB 덮어쓰기·clean·drop은 없다(10 6장).
set -eu
: "${SEELO_ENV_FILE:?production env file required}"
dump=${1:?dump path required}
target_db=${2:?new database name required}
case "$target_db" in seelo_restore_[a-zA-Z0-9_]*) ;; *) echo 'use seelo_restore_ prefix' >&2; exit 2;; esac
case "$target_db" in *[!a-zA-Z0-9_]*) exit 2;; esac
[ -f "$dump" ] || exit 2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
compose_file=${SEELO_COMPOSE_FILE:-$root/docker-compose.prod.yml}
compose() { docker compose --env-file "$SEELO_ENV_FILE" -f "$compose_file" "$@"; }
compose exec -T db pg_restore --list < "$dump" > /dev/null
# 이미 있는 DB면 createdb가 실패하고 멈춘다. 생성한 검증 DB도 자동 삭제하지 않는다.
compose exec -T db createdb -U seelo --template template0 "$target_db"
compose exec -T db pg_restore -U seelo --dbname "$target_db" --no-owner --no-acl --exit-on-error < "$dump"
compose exec -T db psql -X -U seelo -d "$target_db" -v ON_ERROR_STOP=1 \
  -c 'SELECT version_num FROM alembic_version; SELECT count(*) AS users FROM users;'
printf 'restore_verified=%s\n' "$target_db"
