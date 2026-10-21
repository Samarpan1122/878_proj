#!/usr/bin/env bash
# Run from Cloud Build's Docker builder after preparing the image.
set -euo pipefail
image="${1:?Pass the routing image}"
docker run -d --name routing-check "$image"
trap 'docker rm -f routing-check >/dev/null 2>&1 || true' EXIT
for attempt in $(seq 1 30); do
  docker exec routing-check bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080; printf "GET /route/v1/driving/-95.9345,41.2565;-96.0200,41.2600?overview=false HTTP/1.0\r\nHost: localhost\r\n\r\n" >&3; cat <&3' > /workspace/route-smoke.txt 2>/dev/null || true
  if grep -q '"code":"Ok"' /workspace/route-smoke.txt; then break; fi
  sleep 2
done
runtime_uid=$(docker exec routing-check id -u)
if [[ "$runtime_uid" != 65534 ]] || ! grep -q '"code":"Ok"' /workspace/route-smoke.txt; then
  docker logs routing-check
  exit 1
fi
printf 'UID 65534 routing smoke passed; response bytes: '
wc -c < /workspace/route-smoke.txt
