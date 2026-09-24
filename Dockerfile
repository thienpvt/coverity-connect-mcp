FROM python:3.12-slim

WORKDIR /app

# Install the MCP server from the repo root.
RUN pip install --no-cache-dir .

# HTTP transport entrypoint (overrides the package's stdio default).
COPY run_http.py /app/run_http.py

EXPOSE 8000

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

CMD ["python", "/app/run_http.py"]
