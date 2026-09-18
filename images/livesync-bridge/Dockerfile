# livesync-bridge (vrtmrz): mirrors a Self-hosted LiveSync CouchDB vault to a
# directory and back. It has no published image, so this builds it from a
# pinned commit. The bot's vault MCP server reads and writes the mirrored
# directory; see kubernetes/apps/chatops/vault.
FROM docker.io/denoland/deno:2.6.9@sha256:f8ab6f2ae57ae267f2738d3569e624e7844b98268aab0a1c7aef0ba10ef953b0 AS src
ARG BRIDGE_COMMIT=c3760beaa0851214da4860903445d7f6420ca025
USER 0
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN git clone --quiet https://github.com/vrtmrz/livesync-bridge.git . \
    && git checkout --quiet "$BRIDGE_COMMIT" \
    && rm -rf .git \
    && chown -R deno:deno /app \
    && mkdir -p /deno-dir/location_data && chown -R deno:deno /deno-dir
USER 1993
# Deno 2.x: install exactly what deno.lock records.
RUN deno install --frozen

# The config file is rendered at start (it holds the vault passphrase) and
# mounted at /app/dat/config.json; the mirrored vault lives under /app/data.
VOLUME ["/app/dat", "/app/data", "/deno-dir/location_data"]
CMD ["deno", "task", "run"]
