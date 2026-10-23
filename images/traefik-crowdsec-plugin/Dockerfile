# The CrowdSec bouncer plugin's source, for Traefik's local-plugin loader.
#
# Traefik downloads declared plugins from plugins.traefik.io on every start.
# After a power cut the node is usually up before the router has internet, a
# failed download leaves every route that uses the bouncer broken until Traefik
# restarts, and with the bouncer on the entrypoint that is every route, LAN
# included. This image carries the source at a pinned commit instead; an init
# container copies it into an emptyDir that Traefik loads as a local plugin, and
# the image itself sits in the node's containerd cache.
FROM docker.io/alpine/git:v2.54.0@sha256:4fac439ee3b9204bec99c712b8a15942999632458f716ae8149fbb97cb760cd4 AS src
ARG PLUGIN_TAG=v1.7.1
ARG PLUGIN_COMMIT=bef5dfaadbb07381af02ec4e7391e49214ebf953
RUN git clone --quiet --depth 1 --branch "$PLUGIN_TAG" \
        https://github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin.git /plugin \
    && test "$(git -C /plugin rev-parse HEAD)" = "$PLUGIN_COMMIT" \
    && rm -rf /plugin/.git /plugin/.github /plugin/tests /plugin/examples

FROM docker.io/library/busybox:1.38@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e
COPY --from=src /plugin /plugin
# Traefik's pod runs as 65532 under the restricted Pod Security profile.
USER 65532:65532
# Copies the plugin into the volume mounted at /plugins-local, which Traefik
# mounts at plugins-local/src/<moduleName>.
CMD ["cp", "-R", "/plugin/.", "/plugins-local/"]
