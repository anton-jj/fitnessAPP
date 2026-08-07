#!/usr/bin/env bash
#
# Pull the latest published images and restart the stack.
# Run this on the Debian host, from the directory holding docker-compose.prod.yml
# and .env.
#
#   ./deploy.sh                 deploy :latest
#   ./deploy.sh sha-abc123      deploy a specific build (rollback)
#
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE=docker-compose.prod.yml

if [[ ! -f .env ]]; then
  echo "error: no .env here. Copy .env.example and fill it in." >&2
  exit 1
fi

if ! grep -q '^IMAGE_OWNER=' .env; then
  echo "error: .env needs IMAGE_OWNER (lowercase owner/repo, e.g. anton-jj/fitnessapp)" >&2
  exit 1
fi

# An explicit tag argument wins over whatever .env says.
if [[ $# -ge 1 ]]; then
  export IMAGE_TAG="$1"
  echo "==> deploying tag: $IMAGE_TAG"
else
  echo "==> deploying tag: ${IMAGE_TAG:-latest}"
fi

echo "==> pulling images"
docker compose -f "$COMPOSE_FILE" pull

echo "==> starting"
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo "==> waiting for the API to come up"
for _ in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" exec -T api \
      python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" \
      >/dev/null 2>&1; then
    echo "==> healthy"
    docker image prune -f >/dev/null 2>&1 || true
    docker compose -f "$COMPOSE_FILE" ps
    exit 0
  fi
  sleep 2
done

echo "error: API did not become healthy. Recent logs:" >&2
docker compose -f "$COMPOSE_FILE" logs --tail 40 api >&2
exit 1
