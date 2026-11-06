FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

LABEL org.opencontainers.image.title="torproxy" \
      org.opencontainers.image.description="A minimal HTTP proxy routed through Tor" \
      org.opencontainers.image.version="2.1.0" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/hapheus/torproxy" \
      org.opencontainers.image.url="https://github.com/hapheus/torproxy"

RUN apk add --no-cache bash ca-certificates curl privoxy tini tor python3 iptables iptables-legacy libcap \
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

ENV PYTHONPATH=/usr/lib/python3/dist-packages \
    TORPROXY_LISTEN_ADDRESS=0.0.0.0 \
    TORPROXY_LISTEN_PORT=8118 \
    TORPROXY_API_PORT=8080 \
    TORPROXY_SOCKS_PORT=9050

COPY src/torproxy /usr/lib/python3/dist-packages/torproxy
# Ship pyproject.toml so torproxy.__version__ resolves from the single source
# of truth (pyproject.toml) inside the image as well (ISSUE-07).
COPY pyproject.toml /usr/lib/python3/dist-packages/pyproject.toml
COPY --chmod=755 docker/start.sh /usr/local/bin/start.sh
COPY --chmod=755 docker/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY --chmod=644 docker/privoxy.config.template /etc/privoxy/config.template
COPY --chmod=644 docker/torrc /etc/tor/torrc

# ISSUE-03: the container init runs as root only to drop privileges —
# start.sh starts every daemon as an unprivileged user (tor, privoxy,
# torproxy) so the gateway netfilter rules can scope the WAN bypass to
# the dedicated tor UID. No daemon ever runs as root.

EXPOSE 8118 8080 9050

HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]
