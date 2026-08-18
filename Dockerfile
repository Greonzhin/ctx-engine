FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CTX_ENGINE_IN_DOCKER=1 \
    CTX_ENGINE_DATA_DIR=/data \
    CTX_ENGINE_WORKSPACE_ROOT=/workspace

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY ctx_engine /app/ctx_engine
COPY templates /app/templates
RUN pip install --no-cache-dir . \
    && groupadd --system --gid 10001 ctx-engine \
    && useradd --system --uid 10001 --gid ctx-engine --home-dir /app --shell /usr/sbin/nologin ctx-engine \
    && mkdir -p /data /workspace \
    && chown -R 10001:10001 /app /data /workspace

VOLUME ["/workspace", "/data"]
EXPOSE 7331

USER 10001:10001

CMD ["ctx", "serve", "--host", "0.0.0.0", "--port", "7331", "--mode", "safe"]
