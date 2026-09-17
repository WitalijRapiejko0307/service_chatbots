#!/bin/sh
set -eu

strip_slash() {
  printf '%s' "$1" | sed 's:/*$::'
}

if [ -z "${BACKEND_INTERNAL_URL:-}" ]; then
  exec node server.js
fi

BACKEND_INTERNAL_URL="$(strip_slash "$BACKEND_INTERNAL_URL")"
NGINX_LISTEN_PORT="${PORT:-8080}"
export BACKEND_INTERNAL_URL NGINX_LISTEN_PORT

envsubst '${BACKEND_INTERNAL_URL} ${NGINX_LISTEN_PORT}' \
  < /etc/nginx/nginx.frontend.conf.template \
  > /tmp/nginx.conf

nginx -t -c /tmp/nginx.conf

nginx_pid=""
node_pid=""

shutdown() {
  if [ -n "$nginx_pid" ]; then
    kill -TERM "$nginx_pid" 2>/dev/null || true
  fi
  if [ -n "$node_pid" ]; then
    kill -TERM "$node_pid" 2>/dev/null || true
  fi
}
trap shutdown INT TERM

nginx -c /tmp/nginx.conf -g 'daemon off;' &
nginx_pid=$!

PORT=3000 HOSTNAME=127.0.0.1 node server.js &
node_pid=$!

while kill -0 "$node_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 1
done

status=0
if ! kill -0 "$node_pid" 2>/dev/null; then
  wait "$node_pid" || status=$?
else
  status=1
fi
shutdown
wait "$nginx_pid" 2>/dev/null || true
wait "$node_pid" 2>/dev/null || true
exit "$status"
