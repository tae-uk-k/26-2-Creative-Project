#!/bin/sh
set -eu
exec docker compose --env-file /etc/seelo/production.env \
  -f /opt/seelo/current/docker-compose.prod.yml \
  -f /opt/seelo/current/docker-compose.local-ai.yml "$@"
