# Hozur: one image for the web server and the worker.
#   docker build -t hozur .
# See docker/compose.yml for running it with PostgreSQL.

FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN corepack enable && yarn install --frozen-lockfile --non-interactive
COPY frontend/ ./
RUN yarn build

FROM python:3.13-slim
# Pango and HarfBuzz for WeasyPrint (Persian PDF reports); pg_dump / pg_restore for backups
RUN apt-get update \
	&& apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core postgresql-client \
	&& rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 hozur
WORKDIR /app
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/hozur ./hozur
RUN pip install --no-cache-dir .
COPY --from=frontend /src/frontend/dist /app/frontend
ENV HOZUR_FRONTEND_DIST=/app/frontend \
	HOZUR_DATA_DIR=/data \
	PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown hozur:hozur /data
USER hozur
EXPOSE 8000
CMD ["sh", "-c", "hozur db install && hozur serve --host 0.0.0.0 --port 8000"]
