# The claude.ai MCP servers in one image, selected by the container's args:
#   python -m tandoor_mcp   recipes and meal plans, holds the Tandoor token
#   python -m calendar_mcp  Nextcloud calendars over CalDAV, holds an app password
#   python -m vault_mcp     the Obsidian vault, mirrored to a volume
#   python -m opengym_mcp   workouts and weigh-ins in openGym, holds a pairing token
#   python -m mcp_gate      not a server: a token check in front of one that has
#                           none, so claude.ai can reach Snacky
# One image because they share the SDK and the build, and because a manifest
# that names one tag for all of them is one thing to bump.
FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913

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
ARG GIT_SHA=dev
ENV IMAGE_SHA=$GIT_SHA

# Nothing here needs root, and the deployment runs it as 1000 with a
# read-only root filesystem; the servers write nothing to disk.
USER 1000:1000
EXPOSE 8000
CMD ["python", "-m", "tandoor_mcp"]
