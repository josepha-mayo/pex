FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/protocol ./packages/protocol
COPY services/supervisor ./services/supervisor
COPY services/bridge ./services/bridge
RUN uv sync --frozen --no-dev --package pex-supervisor
EXPOSE 8080
CMD ["uv", "run", "python", "-m", "pex_supervisor.runtime"]
