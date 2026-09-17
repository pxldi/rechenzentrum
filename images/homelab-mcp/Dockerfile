# Two MCP servers in one image, selected by the container's args:
#   python -m tandoor_mcp   recipes and meal plans, holds the Tandoor token
#   python -m homelab_mcp   read-only cluster view, holds a ServiceAccount token
# One image because they share the SDK and the build, and because a manifest
# that names one tag for both is one thing to bump.
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# Nothing here needs root, and the deployment runs it as 1000 with a
# read-only root filesystem; the servers write nothing to disk.
USER 1000:1000
EXPOSE 8000
CMD ["python", "-m", "homelab_mcp"]
