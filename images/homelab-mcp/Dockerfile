# Nine MCP servers in one image, selected by the container's args:
#   python -m tandoor_mcp   recipes and meal plans, holds the Tandoor token
#   python -m homelab_mcp   read-only cluster view, holds a ServiceAccount token
#   python -m calendar_mcp  Nextcloud calendars over CalDAV, holds an app password
#   python -m vault_mcp     the Obsidian vault, mirrored to a volume
#   python -m paperless_mcp Paperless documents, holds an API token
#   python -m homeassistant_mcp  Home Assistant states and switches, holds a token
#   python -m immich_mcp    photo search and shared links, holds an API key
#   python -m karakeep_mcp  bookmarks, holds an API key
#   python -m files_mcp     files people send the bot (sidecar in the ZeroClaw pod)
# One image because they share the SDK and the build, and because a manifest
# that names one tag for all of them is one thing to bump.
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# The commit this image was built from, reported by /health as "build".
# ZeroClaw's wait-for-mcp init container runs this same image and waits until
# both Services answer with its own build, so a rollout cannot hand ZeroClaw
# the terminating pod's tool list.
ARG GIT_SHA=dev
ENV IMAGE_SHA=$GIT_SHA

# Nothing here needs root, and the deployment runs it as 1000 with a
# read-only root filesystem; the servers write nothing to disk.
USER 1000:1000
EXPOSE 8000
CMD ["python", "-m", "homelab_mcp"]
