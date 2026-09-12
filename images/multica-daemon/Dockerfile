# The toolchain the Multica agent daemon runs on, as an image layer.
#
# Before this, the daemon was a stock node image and its tools arrived two ways:
# an init container fetched four binaries into an emptyDir at /toolbin, and
# everything else — Go, a second Node, PostgreSQL, Playwright's Chromium — was
# installed by an agent at some point in the past into /data/.local on the PVC.
# The second half is the problem. Those installs are not in any manifest, so the
# environment is a record of what previous agents happened to need rather than
# something this repo describes. A fresh PVC produces a daemon that cannot build
# a Go project or run a browser test, and nothing says so until a task fails on
# the command that needed it.
#
# So the toolchain moves here, where it is reviewed, pinned and rebuilt rather
# than accumulated. /toolbin stays for the three things that genuinely change
# weekly — the multica CLI and the two agent CLIs — and this image holds
# everything that does not.
#
# Debian 13 (trixie) rather than 12, and the reason is PostgreSQL: trixie ships
# 17.10 in its own archive, which is the version already in use, so there is no
# third-party PGDG repository to trust and pin. It also carries a current skopeo
# and ffmpeg. Playwright 1.62 knows trixie and resolves its system libraries
# there without help.
#
# Deliberately absent: docker, terraform, ansible, cloud provider CLIs. The
# browser suite needs a PostgreSQL and a Chromium and has both without a
# container runtime, and neither a privileged pod nor a mounted host socket is
# worth paying for what is already solved.

# SC3040: every RUN below is bash — see the SHELL directive — but hadolint lints
# them as POSIX sh and objects to `set -o pipefail` on principle.
# SC3060: same cause. The JDK stage rewrites 17.0.20+8 into the two spellings
# Adoptium uses in one URL (17.0.20_8 in the filename, %2B in the path), which is
# bash string replacement. Writing them as three separate ARGs would satisfy the
# linter by turning one pinned version into three transcriptions of it — the
# thing the ARG block above exists to avoid.
# DL3003: the tarball stage works in a mktemp directory it deletes afterwards,
# which is the thing WORKDIR cannot express.
# hadolint global ignore=SC3040,SC3060,DL3003

# The digest is the actual pin. The tag is here so a human reading it knows what
# they are looking at, and so Renovate has something to bump.
FROM node:24.19.0-trixie@sha256:66bb8d36ae1ddd72199ed235a089904874ca4079ee517936ca3adb80506a75c1

# Every version is an explicit ARG so that the table in the PR, the pins here and
# the verification transcript are the same three numbers rather than three
# transcriptions of one.
ARG GO_VERSION=1.24.13
ARG GH_VERSION=2.97.0
ARG YQ_VERSION=4.53.3
ARG SQLC_VERSION=1.31.1
ARG GOOSE_VERSION=3.27.3
ARG KUBECTL_VERSION=1.33.13
ARG HELM_VERSION=3.21.3
ARG FLUX_VERSION=2.9.3
ARG KUSTOMIZE_VERSION=5.8.1
ARG STERN_VERSION=1.34.0
ARG K9S_VERSION=0.51.0
ARG KUBECONFORM_VERSION=0.8.0
ARG SOPS_VERSION=3.13.3
ARG AGE_VERSION=1.3.1
ARG CRANE_VERSION=0.21.9
ARG HADOLINT_VERSION=2.15.1
ARG PLAYWRIGHT_VERSION=1.62.1
ARG TEMURIN_VERSION=17.0.20+8
ARG ANDROID_CMDLINE_TOOLS_BUILD=15859902
# 37.0, not 37. Android platform packages carry a minor now — the repository
# publishes android-36.1, android-37.0 and android-37.1, and there is no bare
# android-37 to install. foscal's compileSdk = 37 names no minor, which is .0.
# Getting this wrong fails the build with "Failed to find package", which is
# what the first attempt at this did.
ARG ANDROID_PLATFORM=37.0
ARG ANDROID_BUILD_TOOLS=37.0.0
# AGP's default build-tools trails compileSdk, so a project that names no
# buildToolsVersion asks for this one rather than the one above. Observed: a
# foscal build with compileSdk 37 tried to fetch build-tools;36.0.0 and failed
# against the then read-only SDK. Baking it means the default path needs no
# download at all, which is better than relying on the SDK now being writable.
ARG ANDROID_BUILD_TOOLS_DEFAULT=36.0.0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    GOTOOLCHAIN=local \
    GOROOT=/usr/local/go \
    PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright \
    JAVA_HOME=/usr/local/jdk-17 \
    ANDROID_HOME=/usr/local/android-sdk \
    ANDROID_SDK_ROOT=/usr/local/android-sdk

# --- Debian packages -------------------------------------------------------
#
# Pinned with `=`, which means this build stops rather than drifts when Debian
# issues a point release — the pins are then bumped in a reviewed commit. That
# is the intended failure: an image that silently absorbs a new libc is the
# thing this file exists to stop.
#
# createcluster.conf comes first because postgresql-common's postinst otherwise
# initdb's a main cluster nobody will ever connect to. The daemon's tests bring
# up their own throwaway clusters; a 40 MB one baked into the image is waste.
RUN set -euo pipefail; \
    mkdir -p /etc/postgresql-common; \
    echo 'create_main_cluster = false' > /etc/postgresql-common/createcluster.conf; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        postgresql-17=17.10-0+deb13u1 \
        postgresql-client-17=17.10-0+deb13u1 \
        ffmpeg=7:7.1.5-0+deb13u1 \
        libchromaprint-tools=1.5.1-7 \
        ripgrep=14.1.1-1+b4 \
        jq=1.7.1-6+deb13u3 \
        less=668-1 \
        tree=2.2.1-1 \
        git-lfs=3.6.1-1+deb13u1 \
        zstd=1.5.7+dfsg-1 \
        rsync=3.4.1+ds1-5+deb13u4 \
        shellcheck=0.10.0-1 \
        sqlite3=3.46.1-7+deb13u1 \
        skopeo=1.18.0+ds1-1+b5; \
    rm -rf /var/lib/apt/lists/*

# PostgreSQL's server binaries live in a versioned directory Debian keeps off
# PATH so two majors can coexist. Only one major is installed here, and the
# whole point of this change is that a tool is on PATH for every runtime rather
# than for the one that knew where to look — so they are linked into
# /usr/local/bin with everything else.
RUN set -euo pipefail; \
    for binary in /usr/lib/postgresql/17/bin/*; do \
        ln -sf "$binary" "/usr/local/bin/$(basename "$binary")"; \
    done; \
    initdb --version; pg_ctl --version; psql --version

# --- Go --------------------------------------------------------------------
#
# From go.dev rather than apt: trixie ships 1.24 too, but the daemon builds
# projects that name a specific toolchain, and the tarball is the version this
# repo pinned rather than whichever one Debian is carrying this month.
#
# GOTOOLCHAIN=local, set above, stops the go command silently downloading a
# different toolchain when a go.mod asks for one — a pinned Go that fetches an
# unpinned Go on first use is not pinned.
RUN set -euo pipefail; \
    curl -fsSL -o /tmp/go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"; \
    echo "1fc94b57134d51669c72173ad5d49fd62afb0f1db9bf3f798fd98ee423f8d730  /tmp/go.tar.gz" | sha256sum -c -; \
    tar -C /usr/local -xzf /tmp/go.tar.gz; \
    rm -f /tmp/go.tar.gz; \
    ln -sf /usr/local/go/bin/go /usr/local/bin/go; \
    ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt; \
    # Deliberately not `go version`. Running the go command once writes a
    # telemetry counter under /root/.config whose *filename* contains the date
    # it was written, and deleting it afterwards races the async writer that
    # made it. A layer that cannot produce the same bytes twice, for a file
    # recording nothing anyone wants, is not worth a build-time version string:
    # the tarball is already pinned by its digest above, and CI runs the real
    # `go version` and a cgo build against the finished image.
    test -x /usr/local/go/bin/go

# --- single binaries -------------------------------------------------------
#
# Each one is fetched, checked against the digest upstream published for it, and
# dropped into /usr/local/bin. Two of them — sqlc and age — have digests
# computed from the artifact rather than read from upstream, because upstream
# publishes no checksum listing for them; that is recorded in the PR and in the
# table beside them, not hidden behind an identical-looking line here.
RUN set -euo pipefail; \
    fetch() { \
        curl -fsSL -o "$2" "$1"; \
        echo "$3  $2" | sha256sum -c -; \
    }; \
    fetch "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_amd64" \
        /usr/local/bin/yq fa52a4e758c63d38299163fbdd1edfb4c4963247918bf9c1c5d31d84789eded4; \
    fetch "https://github.com/pressly/goose/releases/download/v${GOOSE_VERSION}/goose_linux_x86_64" \
        /usr/local/bin/goose ca18112e2438b3ad608af9a5938beafd01fa36a4a19a3edbe4f29226ca5c8533; \
    fetch "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
        /usr/local/bin/kubectl 316d712726d857c20744c57cb36aa47cfc79bc0af7e82cebf3780244b654c073; \
    fetch "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64" \
        /usr/local/bin/sops e5bec3346a873ae91d871550f3e698c1aad962aff462a080e40f25fde17fef6b; \
    fetch "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-linux-x86_64" \
        /usr/local/bin/hadolint c7187db94eeeeca956519a6af171adc31453941a1e777961f6e680f697c8c507; \
    chmod 0755 /usr/local/bin/yq /usr/local/bin/goose /usr/local/bin/kubectl \
        /usr/local/bin/sops /usr/local/bin/hadolint

# --- tarballs --------------------------------------------------------------
RUN set -euo pipefail; \
    work=$(mktemp -d); cd "$work"; \
    get() { curl -fsSL -o "$2" "$1"; echo "$3  $2" | sha256sum -c -; }; \
    \
    get "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
        gh.tgz a2c9b8497e1f85b1ad0dfcb78b5a622e098801b8e461e459e88e1ee12f018112; \
    tar -xzf gh.tgz --strip-components=2 "gh_${GH_VERSION}_linux_amd64/bin/gh"; \
    \
    get "https://github.com/sqlc-dev/sqlc/releases/download/v${SQLC_VERSION}/sqlc_${SQLC_VERSION}_linux_amd64.tar.gz" \
        sqlc.tgz 497ae4fcdfa64c5b0c311ffe4c2bd991e43991e82e5367792ed78bc2dca27354; \
    tar -xzf sqlc.tgz sqlc; \
    \
    get "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz" \
        helm.tgz 15e041a93a590dce8100f39385cd98c84a765c9e36aeeb9e2dc6ff9e4769e2e0; \
    tar -xzf helm.tgz --strip-components=1 linux-amd64/helm; \
    \
    get "https://github.com/fluxcd/flux2/releases/download/v${FLUX_VERSION}/flux_${FLUX_VERSION}_linux_amd64.tar.gz" \
        flux.tgz eae4e8608c0ade2bf4e8dec1669dbb6b0c28b5822b252d97feccfb4fb1181fd2; \
    tar -xzf flux.tgz flux; \
    \
    get "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv${KUSTOMIZE_VERSION}/kustomize_v${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
        kustomize.tgz 029a7f0f4e1932c52a0476cf02a0fd855c0bb85694b82c338fc648dcb53a819d; \
    tar -xzf kustomize.tgz kustomize; \
    \
    get "https://github.com/stern/stern/releases/download/v${STERN_VERSION}/stern_${STERN_VERSION}_linux_amd64.tar.gz" \
        stern.tgz 7754adfa653939240f7d20fff4ada9b69cda40c9e70732301f67bb8045f1ef3e; \
    tar -xzf stern.tgz stern; \
    \
    get "https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_amd64.tar.gz" \
        k9s.tgz c3752ad51a5a4015a113819c4eeb6e55a4d0e4b8e652494797532f6fc8161dd7; \
    tar -xzf k9s.tgz k9s; \
    \
    get "https://github.com/yannh/kubeconform/releases/download/v${KUBECONFORM_VERSION}/kubeconform-linux-amd64.tar.gz" \
        kubeconform.tgz 9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883; \
    tar -xzf kubeconform.tgz kubeconform; \
    \
    get "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" \
        age.tgz bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377; \
    tar -xzf age.tgz --strip-components=1 age/age age/age-keygen; \
    \
    get "https://github.com/google/go-containerregistry/releases/download/v${CRANE_VERSION}/go-containerregistry_Linux_x86_64.tar.gz" \
        crane.tgz 5c16d8ddb971cb1d5e6ed8b1e743da8224414eeba2c2762d8f1a61b2f095699e; \
    tar -xzf crane.tgz crane; \
    \
    install -m 0755 gh sqlc helm flux kustomize stern k9s kubeconform age age-keygen crane /usr/local/bin/; \
    cd /; rm -rf "$work"

# --- JDK 17 ----------------------------------------------------------------
#
# From Adoptium rather than apt, and 17 rather than whatever is newest, because
# both halves are forced:
#
#   trixie carries no openjdk-17 at all — only 21 (21.0.12) and 25 (25.0.4). So
#   there is no apt pin to write here even if one were preferred.
#
#   17 specifically because foscal's core/core-model/build.gradle.kts calls
#   jvmToolchain(17). A toolchain request is not a floor Gradle rounds up from:
#   with only a 21 on the machine it fails with "no matching toolchain" rather
#   than compiling. Gradle can provision a JDK itself, but that means an
#   unpinned JDK downloaded at build time into the runtime user's HOME, which is
#   the same objection GOTOOLCHAIN=local answers for Go above.
#
# 17 also runs Gradle itself (9.6.1 via the wrapper, so no Gradle is installed
# here) and satisfies AGP 9.3.1, whose floor is 17. One JDK covers both roles.
RUN set -euo pipefail; \
    tarball="OpenJDK17U-jdk_x64_linux_hotspot_${TEMURIN_VERSION/+/_}.tar.gz"; \
    curl -fsSL -o /tmp/jdk.tar.gz \
        "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-${TEMURIN_VERSION/+/%2B}/${tarball}"; \
    echo "be7668bc030d578b83d6d5ef9221d6d6729bbbca8cf94a7d52e16ac68b5a5a35  /tmp/jdk.tar.gz" | sha256sum -c -; \
    mkdir -p "$JAVA_HOME"; \
    tar -C "$JAVA_HOME" --strip-components=1 -xzf /tmp/jdk.tar.gz; \
    rm -f /tmp/jdk.tar.gz; \
    for binary in java javac jar keytool jshell; do \
        ln -sf "$JAVA_HOME/bin/$binary" "/usr/local/bin/$binary"; \
    done; \
    java -version; javac -version

# --- Android SDK -----------------------------------------------------------
#
# foscal is an Android application (AGP 9.3.1, Compose, Hilt/KSP), so a JDK on
# its own gets as far as "SDK location not found" and no further.
#
# Only the four components a headless build actually reads:
#   cmdline-tools   sdkmanager itself, and what AGP shells out to
#   platform-tools  adb, which the build references even when nothing is plugged in
#   platforms;37    compileSdk 37, from app/build.gradle.kts
#   build-tools;37  aapt2/d8/zipalign for that platform
#
# Deliberately absent: emulator and system-images. Together they are larger than
# everything else in this file combined, and an emulator needs /dev/kvm, which
# this pod does not have and should not get. Instrumented tests belong on real
# hardware or a runner built for them; unit tests and assembleDebug do not need
# either.
#
# The licence acceptance is not a formality that can be skipped — an unaccepted
# licence makes every build fail with a message about running sdkmanager
# interactively, which is unanswerable in a container. Accepting at build time is
# the only place it can happen once rather than per-PVC.
#
# Owned by the runtime uid, which reverses the decision this comment used to
# argue for. The original reasoning — root-owned, so a session cannot mutate it
# and the SDK is identical on every restart — was correct about the mechanism
# and wrong about the cost.
#
# AGP installs missing components itself, and its default build-tools version
# trails compileSdk, so a build that names no buildToolsVersion asks for
# build-tools;36.0.0 and fails on a read-only SDK. That is not a one-off:
# every new AGP, dependency or platform target can want a component that was
# not baked, and each one fails the same way. Pinning buildToolsVersion in the
# project works around exactly one instance of it.
#
# The immutability being given up is smaller than it looks. $ANDROID_HOME is an
# image layer, not the PVC, so anything sdkmanager adds at runtime is discarded
# on the next restart anyway — this makes a build self-heal rather than making
# the SDK permanently mutable. What it costs is a re-download after each
# restart for components that are not baked here. If that churn becomes
# noticeable, the fix is to bake the component, not to re-freeze the directory.
#
# 1000:1000 numerically rather than node:node: this stage runs before any
# assumption about the base image's user table is worth relying on, and the
# runtime uid is what the Deployment pins.
#
# unzip is not in the apt list above because it arrives with the node base
# image; that image is pinned by digest, so it cannot disappear without a
# reviewed bump, the same way Playwright's system libraries are pinned.
RUN set -euo pipefail; \
    curl -fsSL -o /tmp/cmdline-tools.zip \
        "https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDLINE_TOOLS_BUILD}_latest.zip"; \
    echo "4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583  /tmp/cmdline-tools.zip" | sha256sum -c -; \
    mkdir -p "$ANDROID_HOME/cmdline-tools"; \
    unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools"; \
    rm -f /tmp/cmdline-tools.zip; \
    # sdkmanager insists on living at cmdline-tools/<channel>/bin and refuses to
    # run from the path the zip actually unpacks to.
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"; \
    # pipefail is on for every RUN here (see SHELL above) and disagrees with
    # `yes |`: sdkmanager stops reading once the last licence is answered, yes
    # takes SIGPIPE, and the pipeline reports 141 even though sdkmanager
    # succeeded. That failed the build the first time this was merged.
    #
    # pipefail is turned off for this one pipeline rather than the whole stage,
    # and `|| true` is deliberately not used: with pipefail off the pipeline
    # reports its last command, so a licence sdkmanager genuinely could not
    # accept still fails the build through set -e.
    set +o pipefail; \
    yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses >/dev/null; \
    set -o pipefail; \
    "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
        "platform-tools" \
        "build-tools;${ANDROID_BUILD_TOOLS_DEFAULT}" \
        "platforms;android-${ANDROID_PLATFORM}" \
        "build-tools;${ANDROID_BUILD_TOOLS}" >/dev/null; \
    for binary in sdkmanager avdmanager; do \
        ln -sf "$ANDROID_HOME/cmdline-tools/latest/bin/$binary" "/usr/local/bin/$binary"; \
    done; \
    ln -sf "$ANDROID_HOME/platform-tools/adb" /usr/local/bin/adb; \
    chown -R 1000:1000 "$ANDROID_HOME"; \
    chmod -R a+rX "$ANDROID_HOME"; \
    sdkmanager --version; adb --version

# --- Playwright ------------------------------------------------------------
#
# Chromium and its system libraries, baked where every user can read them rather
# than under the runtime user's HOME on the PVC. The daemon runs as uid 1000 and
# nothing here is writable by it, which is correct: a browser the pod cannot
# silently re-download is a browser that is the same on every restart.
#
# Only chromium. Firefox and WebKit triple the layer and nothing here drives
# them; `playwright install firefox` still works at runtime for anyone who needs
# one, it just is not paid for by every pull.
#
# `install-deps` resolves its 60-odd system libraries from the base image's own
# suite, so those are pinned by the base digest above rather than one by one —
# the alternative is re-pinning sixty lines on every Debian point release, which
# nobody would keep doing. This is the one deliberate exception to the pin-it-all
# rule and it is called out in the PR.
#
# The library is installed globally beside the browsers, not fetched by npx and
# thrown away, so that `playwright` is a command on PATH like everything else
# here and the version that placed the browsers is the version that can be asked
# what it placed. A project with its own playwright in node_modules still uses
# that one; this is the floor, not a ceiling.
#
# One coupling to know about: a browser build belongs to a Playwright minor. A
# project pinned to a distant version will ask for a revision that is not baked
# and try to download it into a directory the runtime uid cannot write, which
# fails rather than silently using the wrong browser. That is the safer failure,
# and the fix is to point PLAYWRIGHT_BROWSERS_PATH at a writable path for that
# task or to move this pin.
RUN set -euo pipefail; \
    npm install -g "playwright@${PLAYWRIGHT_VERSION}"; \
    playwright install --with-deps chromium; \
    rm -rf /var/lib/apt/lists/* /root/.npm; \
    chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH"

# The npm cache the daemon writes at runtime is redirected to the PVC by the
# Deployment; this is only for anything that reads it before that env lands.
ENV npm_config_cache=/tmp/npm-cache

# A last look at the two things that are easy to get wrong and impossible to
# notice: that /usr/local/bin is reachable from a PATH nobody customised, and
# that the runtime uid can read the browser. Failing here fails the build rather
# than the first task that needed them.
RUN set -euo pipefail; \
    env -i /bin/sh -lc 'command -v go kubectl psql fpcalc rg jq crane java javac sdkmanager adb >/dev/null' \
        || { echo "a baked tool is not on the default PATH" >&2; exit 1; }; \
    test -r "$(find "$PLAYWRIGHT_BROWSERS_PATH" -name headless_shell -o -name chrome | head -1)"; \
    # JAVA_HOME and ANDROID_HOME are ENV, so they survive into every runtime —
    # but a Gradle build reads the directories, not the variables, and a broken
    # symlink farm would still pass the PATH check above.
    test -x "$JAVA_HOME/bin/java"; \
    test -d "$ANDROID_HOME/platforms/android-${ANDROID_PLATFORM}"; \
    test -d "$ANDROID_HOME/build-tools/${ANDROID_BUILD_TOOLS}"; \
    # The licences are the failure that only shows up on someone else's first
    # build, so prove they were accepted rather than assuming the yes | took.
    test -d "$ANDROID_HOME/licenses"
