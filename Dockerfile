FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOCALDDI_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY localddi ./localddi
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --home-dir /app localddi \
    && mkdir -p /data && chown localddi /data

USER localddi
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"

CMD ["localddi", "serve", "--host", "0.0.0.0", "--port", "8080"]
