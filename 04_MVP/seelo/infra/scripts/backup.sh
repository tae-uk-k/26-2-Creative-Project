#!/bin/sh
# 매일 KST 04:00. BACKUP_DIR은 VM 밖 저장소의 마운트 경로(10 6장).
set -eu
umask 077
: "${SEELO_ENV_FILE:?production env file required}"
: "${BACKUP_DIR:?off-host mounted backup directory required}"
keep=${BACKUP_KEEP_DAYS:-7}
case "$keep" in ''|*[!0-9]*) echo 'invalid BACKUP_KEEP_DAYS' >&2; exit 2;; esac
[ "$keep" -ge 1 ] || exit 2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
compose_file=${SEELO_COMPOSE_FILE:-$root/docker-compose.prod.yml}
[ -d "$BACKUP_DIR" ] || { echo 'BACKUP_DIR must already be mounted' >&2; exit 2; }
backup_dir=$(CDPATH= cd -- "$BACKUP_DIR" && pwd)
[ "$backup_dir" != / ] || exit 2
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$backup_dir/seelo_$stamp.dump"
# 기존 파일을 덮어쓰지 않고, 실패한 중간 파일도 지우지 않는다.
set -C
docker compose --env-file "$SEELO_ENV_FILE" -f "$compose_file" exec -T db \
  pg_dump -U seelo -d seelo -Fc --no-owner --no-acl > "$target.partial"
test -s "$target.partial"
docker compose --env-file "$SEELO_ENV_FILE" -f "$compose_file" exec -T db \
  pg_restore --list < "$target.partial" > "$target.list"
mv -n -- "$target.partial" "$target"
# 7일 지난 이 스크립트의 백업은 격리한다. 영구 삭제는 하지 않는다.
mkdir -p -- "$backup_dir/quarantine"
find "$backup_dir" -maxdepth 1 -type f -name 'seelo_????????T??????Z.dump' -mmin "+$((keep * 1440))" \
  -exec sh -c 'base=$1; shift; for file do
    mv -n -- "$file" "$base/quarantine/"
    if [ -f "$file.list" ]; then mv -n -- "$file.list" "$base/quarantine/"; fi
    printf "backup_quarantined=%s/quarantine/%s\n" "$base" "$(basename -- "$file")"
  done' sh "$backup_dir" {} +
printf 'backup_created=%s\n' "$target"
