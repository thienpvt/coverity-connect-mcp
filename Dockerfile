FROM python:3.12-slim

WORKDIR /app

# Install the MCP server from the repo root.
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

CMD ["python", "/app/run_http.py"]
