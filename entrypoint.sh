#!/bin/bash
set -e

if [ -d /app/logs ]; then
    chown -R nodehr:nodehr /app/logs 2>/dev/null || true
    chmod -R 755 /app/logs 2>/dev/null || true
fi

exec gosu nodehr "$@"
