# Fingerprints the music library and compares each file's tags with what
# AcoustID says the audio is (kubernetes/apps/media/music-audit). fpcalc and
# mutagen come from Debian, so nothing is fetched outside apt.
FROM docker.io/library/debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0

# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates libchromaprint-tools python3 python3-mutagen \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 music_audit.py /usr/local/bin/music-audit

# 568 is the media namespace's file owner; the library is world-readable.
USER 568:568
ENTRYPOINT ["music-audit"]
CMD ["scan"]
