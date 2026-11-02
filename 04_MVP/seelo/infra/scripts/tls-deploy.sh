#!/bin/sh
# Certbot deploy hook. Root owns the installed copy and the production env.
set -eu
umask 077

release_dir=${SEELO_RELEASE_DIR:-/opt/seelo/current}
env_file=${SEELO_ENV_FILE:-/etc/seelo/production.env}
tls_dir=${SEELO_TLS_DIR:-/etc/seelo/tls}
host=${SEELO_TLS_HOST:-seelo.site}
lineage=${RENEWED_LINEAGE:-/etc/letsencrypt/live/seelo.site}

if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'Run this hook as root.' >&2
  exit 1
fi
if [ "$lineage" != "/etc/letsencrypt/live/$host" ]; then
  printf '%s\n' 'Unrelated certificate; no changes.'
  exit 0
fi

openssl x509 -in "$lineage/fullchain.pem" -noout -checkend 3600
openssl x509 -in "$lineage/fullchain.pem" -noout -checkhost "$host"
openssl x509 -in "$lineage/fullchain.pem" -noout -checkhost "www.$host"
cert_key=$(openssl x509 -in "$lineage/fullchain.pem" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
private_key=$(openssl pkey -in "$lineage/privkey.pem" -pubout -outform DER | sha256sum)
if [ "$cert_key" != "$private_key" ]; then
  printf '%s\n' 'Certificate and private key do not match.' >&2
  exit 1
fi

install -d -m 0700 "$tls_dir"
previous=
if [ -f "$tls_dir/fullchain.pem" ] && [ -f "$tls_dir/privkey.pem" ]; then
  previous=$(mktemp -d "$tls_dir/previous.XXXXXXXX")
  install -m 0644 "$tls_dir/fullchain.pem" "$previous/fullchain.pem"
  install -m 0600 "$tls_dir/privkey.pem" "$previous/privkey.pem"
fi
install -m 0644 "$lineage/fullchain.pem" "$tls_dir/fullchain.pending.pem"
install -m 0600 "$lineage/privkey.pem" "$tls_dir/privkey.pending.pem"
mv "$tls_dir/fullchain.pending.pem" "$tls_dir/fullchain.pem"
mv "$tls_dir/privkey.pending.pem" "$tls_dir/privkey.pem"

compose() {
  docker compose --env-file "$env_file" -f "$release_dir/docker-compose.prod.yml" "$@"
}
if [ -z "$(compose ps --status running -q web)" ]; then
  printf '%s\n' 'TLS files staged; web service is not running yet.'
  exit 0
fi
if ! compose exec -T web nginx -t </dev/null; then
  if [ -n "$previous" ]; then
    install -m 0644 "$previous/fullchain.pem" "$tls_dir/fullchain.pem"
    install -m 0600 "$previous/privkey.pem" "$tls_dir/privkey.pem"
  fi
  printf '%s\n' 'nginx validation failed; previous TLS files preserved.' >&2
  exit 1
fi
compose exec -T web nginx -s reload </dev/null
printf '%s\n' 'TLS files installed and nginx reloaded.'
