FROM python:3.11-slim

WORKDIR /app

# claude CLI (native build) — handlers shell out to `claude -p` for post
# generation. Auth comes from the CLAUDE_CODE_OAUTH_TOKEN Fly secret.
# tini: real PID 1 so SIGTERM reaches both processes and zombies get reaped.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed model at build time into the same persistent cache
# path used by memory.embeddings at runtime.
ENV FASTEMBED_CACHE_DIR=/root/.cache/mindpattern/fastembed
RUN mkdir -p "$FASTEMBED_CACHE_DIR" \
    && python3 -c "import os; from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir=os.environ['FASTEMBED_CACHE_DIR'])"

# Slack bot + dashboard + the modules they import. harness/ is deliberately
# excluded — harness commands only run on the Mac.
COPY slack_bot/ slack_bot/
COPY dashboard/ dashboard/
COPY orchestrator/ orchestrator/
COPY social/ social/
COPY memory/ memory/
COPY policies/ policies/
COPY agents/ agents/
# users.json (subscriber PII) and social-config.json (phone number) are NOT
# baked into the image — start.sh symlinks them from the /data volume.
COPY config.json .
COPY CLAUDE.md .
COPY start.sh .

# Fly.io mounts the volume at /data, but code resolves paths relative to the
# project root (/app/data/...). memory.db, reports, and vault identity files
# (voice.md, soul.md) arrive on the volume via orchestrator/sync.py daily.
RUN ln -sf /data /app/data && ln -sf /data/reports /app/reports

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data
ENV USERS_JSON=/data/users.json
ENV HOST=0.0.0.0
ENV PORT=8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "start.sh"]
