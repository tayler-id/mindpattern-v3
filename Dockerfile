FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed model at build time so cold starts don't fetch 22MB
RUN python3 -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Copy the FastAPI dashboard and its dependencies
COPY dashboard/ dashboard/
COPY orchestrator/ orchestrator/
COPY social/ social/
COPY memory/ memory/
# reports/ lives on the Fly.io volume at /data — symlinked via /app/data
# Symlink /app/reports -> /data/reports so the API can find them
RUN ln -sf /data/reports /app/reports
COPY users.json .
COPY social-config.json .
COPY config.json .

# Fly.io mounts the volume at /data, but the app resolves paths relative to
# the project root (/app/data/...). Symlink so both paths work.
RUN ln -sf /data /app/data

ENV HOST=0.0.0.0
ENV PORT=8080
ENV DATA_DIR=/data
ENV USERS_JSON=/data/users.json

CMD ["python3", "-m", "uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8080"]
