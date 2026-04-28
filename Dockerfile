FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json tsconfig.json vite.config.ts postcss.config.js tailwind.config.ts ./
COPY frontend ./frontend

RUN npm ci
RUN npm run build


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    IMAGE_PROMPT_LIBRARY_PATH=/data/library \
    IMPORT_DEMO_DATA_ON_START=0

WORKDIR /app

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY backend ./backend
COPY scripts ./scripts
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN chmod +x ./scripts/entrypoint.sh && pip install --no-cache-dir .

EXPOSE 8000

CMD ["./scripts/entrypoint.sh"]
