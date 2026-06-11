#!/bin/bash
# Fly.io entrypoint: run the dashboard API and the Slack bot in the same
# machine. tini is PID 1 (Dockerfile ENTRYPOINT) and forwards SIGTERM here;
# the trap passes it to both children so the bot's graceful shutdown runs.
# If either process dies on its own, exit nonzero so Fly restarts the machine.
set -m

# PII config lives on the volume, not in the image (M0 task 9).
ln -sf /data/social-config.json /app/social-config.json
ln -sf /data/users.json /app/users.json

python3 -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8080 &
UVICORN_PID=$!
python3 -m slack_bot &
BOT_PID=$!

graceful() {
    kill -TERM "$UVICORN_PID" "$BOT_PID" 2>/dev/null
    wait
    exit 0
}
trap graceful TERM INT

wait -n
exit 1
