FROM node:22-alpine AS webui-build

WORKDIR /web

COPY package.json package-lock.json tsconfig.json vite.config.ts ./
COPY api/webui ./api/webui

RUN npm install
RUN npm run build

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON=3.11 \
    UV_CACHE_DIR=/app/.uv-cache \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

COPY . .
COPY --from=webui-build /web/api/webui/dist ./api/webui/dist

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
