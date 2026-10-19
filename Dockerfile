FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/instance /app/logs /app/app/static/uploads /app/app/static/models/products \
    && chown -R app:app /app

COPY --chown=app:app . .

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:5000/', timeout=3)" || exit 1

CMD ["waitress-serve", "--listen=0.0.0.0:5000", "run:app"]