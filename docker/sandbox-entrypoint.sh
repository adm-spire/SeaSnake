#!/bin/sh
# Seed the writable cargo cache from the read-only image cache. This lets us
# run containers with --read-only while cargo still has a writable CARGO_HOME.
set -eu

if [ -n "${CARGO_HOME:-}" ] && [ ! -d "$CARGO_HOME/registry" ]; then
    mkdir -p "$CARGO_HOME"
    cp -a /opt/cargo-cache/. "$CARGO_HOME"/ 2>/dev/null || true
fi

exec "$@"
