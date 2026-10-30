FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
RUN useradd --uid 10001 --create-home contextgraph
USER 10001
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "context_knowledge_graph.api:app", "--host", "0.0.0.0", "--port", "8000"]
