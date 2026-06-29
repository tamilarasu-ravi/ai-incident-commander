#!/bin/sh
set -e

# Local dev sidecar: Redis in the same container as the app (bind localhost only).
redis-server --daemonize yes --bind 127.0.0.1 --port 6379 --save ""

exec "$@"
