FROM python:3.11-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir build && \
    python -m build --wheel

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    pip install --no-cache-dir briq[studio] && \
    rm -rf /tmp/*.whl

RUN addgroup --system --gid 1001 briq && \
    adduser --system --uid 1001 --gid 1001 briq && \
    mkdir -p /data /projects && \
    chown -R briq:briq /app /data /projects

VOLUME ["/data", "/projects"]

EXPOSE 8765

USER briq

ENV BRIQ_STUDIO_DATA=/data \
    BRIQ_STUDIO_HOST=0.0.0.0 \
    BRIQ_STUDIO_PORT=8765

CMD ["briq-studio"]
