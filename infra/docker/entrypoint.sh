#!/bin/sh
set -e

if [ -n "$GIT_REPO" ]; then
    if [ -d /app/project ]; then
        rm -rf /app/project
    fi
    git clone "$GIT_REPO" /app/project
    cd /app/project
elif [ -d /app/project ]; then
    cd /app/project
fi

exec "$@"
