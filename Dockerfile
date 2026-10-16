FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[voice]"
COPY agents agents
COPY api api
COPY scripts scripts
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
