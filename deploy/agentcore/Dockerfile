FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8080

COPY packages/protocol /app/packages/protocol
COPY services/supervisor /app/services/supervisor

RUN pip install --no-cache-dir ./packages/protocol ./services/supervisor

EXPOSE 8080
CMD ["python", "-m", "pex_supervisor.runtime"]
