FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 GEOCRASH_SAFETY_DATA=/app/data/safety
WORKDIR /app
COPY requirements-safety.txt requirements-safety.lock ./
RUN pip install --no-cache-dir -r requirements-safety.txt -c requirements-safety.lock && useradd --uid 10001 --create-home safety
COPY --chown=safety:safety safety/ ./safety/
COPY --chown=safety:safety infra/postgis.sql ./infra/postgis.sql
COPY --chown=safety:safety web/static/safety* ./web/static/
COPY --chown=safety:safety web/static/tokens.css ./web/static/tokens.css
COPY --chown=safety:safety data/safety/ ./data/safety/
USER safety
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready',timeout=3)"
CMD ["sh", "-c", "exec uvicorn safety.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
