FROM python:3.12-slim
ARG TARGETARCH
RUN test "${TARGETARCH}" = "arm64"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PEX_RUNTIME_SERVER=agentcore \
    PEX_SUPERVISOR_WALL_TIMEOUT=20 \
    PYTHONPATH=/app/packages/protocol/src:/app/services/supervisor/src

COPY deploy/agentcore/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

COPY packages/protocol /app/packages/protocol
COPY services/supervisor /app/services/supervisor

# Run the copied source directly. Building local wheels here would let pip create
# an unpinned build-isolation environment outside requirements.lock.
RUN python -c "import pex_protocol, pex_supervisor.runtime" \
    && useradd --system --uid 10001 --create-home pex

EXPOSE 8080
USER 10001
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2).read()"]
CMD ["python", "-m", "pex_supervisor.runtime"]
