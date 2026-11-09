# Headless Godot for the survivorlike game's balance benches and autopilot
# training (kubernetes/apps/survivorlike-bench). The game is not in the image:
# each Job fetches the commit it should measure, so one image serves every
# branch and the game repository stays private.
#
# Ubuntu 26.04 because the game's committed native library
# (game/bin/linux/libsurvivorlike_native.so) is built on a rolling distribution
# and needs glibc 2.43. Debian 13 has 2.41, and with an older glibc Godot does
# not fail: it skips the library and the horde runs in GDScript, slower and
# without any error. bench-job checks for that before the first run.
FROM docker.io/library/ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c

# The version the game is developed on. Not tracked by Renovate: the engine
# moves when the game moves, in a PR that changes both.
ARG GODOT_VERSION=4.7.2
ARG GODOT_SHA512=9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# tzdata: night_bench.py's --until is local time, and the queue is written in
# Berlin time.
# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl git openssh-client python3 python3-numpy unzip \
        libfontconfig1 tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/godot.zip \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip" \
    && echo "${GODOT_SHA512}  /tmp/godot.zip" | sha512sum -c - \
    && unzip -q /tmp/godot.zip -d /tmp/godot \
    && install -m 0755 "/tmp/godot/Godot_v${GODOT_VERSION}-stable_linux.x86_64" /usr/local/bin/godot \
    && rm -rf /tmp/godot /tmp/godot.zip

COPY ssh_config /etc/ssh/ssh_config.d/github.conf
COPY github_known_hosts /etc/ssh/github_known_hosts
COPY bench-job /usr/local/bin/bench-job

# The pod mounts an emptyDir here; owning it in the image too lets the image
# run under plain docker for a local test.
RUN mkdir -p /work/home && chown -R 1000:1000 /work

# Numeric, so the pod's runAsNonRoot can check it (hadolint DL3066 too).
USER 1000
ENV HOME=/work/home \
    TZ=Europe/Berlin \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/bench-job"]
