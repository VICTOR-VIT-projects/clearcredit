# Public, read-only ClearCredit API. Build from the repo root:
#   docker compose -f deploy/docker-compose.yml up -d --build
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# Dependencies come from pyproject.toml; the lockfile is used as constraints, so its
# Windows-only pins (pywin32, colorama) are ignored on Linux instead of breaking the build.
COPY backend/pyproject.toml backend/requirements-lock.txt backend/
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('backend/pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
 && pip install -c backend/requirements-lock.txt -r /tmp/req.txt

COPY backend/app backend/app
COPY data/cache data/cache

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app && mkdir /srv/state && chown app /srv/state
USER app
WORKDIR /srv/backend

ENV HOME=/tmp \
    CLEARCREDIT_READ_ONLY=1 \
    CLEARCREDIT_NO_ENV=1 \
    CLEARCREDIT_DB=/srv/state/clearcredit.sqlite3 \
    RATE_LIMIT_PER_MINUTE=120

EXPOSE 8090
HEALTHCHECK --interval=60s --timeout=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=8)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8090"]
