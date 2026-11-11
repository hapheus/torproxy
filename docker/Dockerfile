FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

# ISSUE-15 (#79): the image Python is pinned here and mirrored in the CI
# matrix (.github/workflows/pr-gate.yml). Bump both together; the build
# fails fast if the packaged interpreter drifts from this version.
ARG PYTHON_VERSION=3.14

LABEL org.opencontainers.image.title="torproxy" \
      org.opencontainers.image.description="A minimal HTTP proxy routed through Tor" \
      org.opencontainers.image.version="2.7.5" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/hapheus/torproxy" \
      org.opencontainers.image.url="https://github.com/hapheus/torproxy" \
      io.modelcontextprotocol.server.name="io.github.hapheus/torproxy"

RUN apk add --no-cache bash ca-certificates curl privoxy tini tor "python3~${PYTHON_VERSION}" iptables iptables-legacy libcap \
    && python3 --version \
    && python3 -c "import sys, sysconfig; print(f'Python {sys.version}'); print(f'Site-packages (purelib): {sysconfig.get_paths()[\"purelib\"]}')" \
    && PYTHON_VERSION="${PYTHON_VERSION}" python3 -c "import os, sys; expected = tuple(int(part) for part in os.environ['PYTHON_VERSION'].split('.')); assert sys.version_info[:len(expected)] == expected, f'Unexpected Python {sys.version}; expected Python {os.environ[\"PYTHON_VERSION\"]}'" \
    && addgroup -S torproxy \
    && adduser -S -h /var/lib/tor -s /sbin/nologin -G torproxy torproxy \
    && addgroup torproxy privoxy \
    && addgroup tor torproxy \
    && install -d -m 0755 -o torproxy -g torproxy /etc/privoxy \
    && install -d -m 0750 -o tor -g torproxy /var/lib/tor \
    && install -d -o privoxy -g privoxy /var/log/privoxy \
    && ln -sf /sbin/tini /usr/bin/tini \
    && setcap cap_net_admin,cap_net_raw+ep /usr/sbin/xtables-nft-multi \
    && setcap cap_net_admin,cap_net_raw+ep /usr/sbin/xtables-legacy-multi

# ISSUE-15 (#79): torproxy is installed into sysconfig's purelib (Alpine:
# /usr/lib/python3.14/site-packages), which is already on Python's default
# sys.path, so no PYTHONPATH is needed. The previous
# /usr/lib/python3/dist-packages path is Debian-specific and does not exist
# on Alpine.
ENV PYTHON_VERSION=${PYTHON_VERSION} \
    TORPROXY_LISTEN_ADDRESS=0.0.0.0 \
    TORPROXY_LISTEN_PORT=8118 \
    TORPROXY_API_PORT=8080 \
    TORPROXY_SOCKS_PORT=9050 \
    TORPROXY_MCP_PORT=2501 \
    TORPROXY_MCP_ENABLED=true

# Stage sources, then install into the sysconfig-derived site-packages so the
# layout follows the interpreter actually present in the image (ISSUE-15).
COPY src/torproxy /app/torproxy-src
# Ship pyproject.toml so torproxy.__version__ resolves from the single source
# of truth (pyproject.toml) inside the image as well (ISSUE-07).
COPY pyproject.toml /app/pyproject.toml
RUN SITE_PACKAGES="$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && echo "Installing torproxy into $SITE_PACKAGES" \
    && mkdir -p "$SITE_PACKAGES" \
    && cp -a /app/torproxy-src "$SITE_PACKAGES/torproxy" \
    && cp /app/pyproject.toml "$SITE_PACKAGES/pyproject.toml" \
    && printf '#!/usr/bin/env python3\nimport sys\nfrom torproxy.runtime.cli import main\nif __name__ == "__main__":\n    sys.exit(main())\n' > /usr/local/bin/torproxy \
    && chmod 0755 /usr/local/bin/torproxy \
    && rm -rf /app \
    && python3 -c "import torproxy; print(f'torproxy {torproxy.__version__} import OK on Python ' + __import__('sys').version)" \
    && torproxy --version
COPY --chmod=755 docker/start.sh /usr/local/bin/start.sh
COPY --chmod=755 docker/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY --chmod=644 docker/privoxy.config.template /etc/privoxy/config.template
COPY --chmod=644 docker/torrc /etc/tor/torrc

# ISSUE-03: the container init runs as root only to drop privileges —
# start.sh starts every daemon as an unprivileged user (tor, privoxy,
# torproxy) so the gateway netfilter rules can scope the WAN bypass to
# the dedicated tor UID. No daemon ever runs as root.

EXPOSE 8118 8080 9050 2501

HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]
