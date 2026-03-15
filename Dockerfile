FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed model at build time so cold starts don't fetch 22MB
RUN python3 -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

COPY server.py .
COPY users.json .

ENV HOST=0.0.0.0
ENV PORT=8080
ENV DATA_DIR=/data
ENV USERS_JSON=/data/users.json

CMD ["python3", "server.py"]
