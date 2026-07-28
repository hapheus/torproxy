FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="torproxy" \
      org.opencontainers.image.description="A minimal HTTP proxy routed through Tor" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/hapheus/torproxy" \
      org.opencontainers.image.url="https://github.com/hapheus/torproxy"

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl privoxy tini tor \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --home-dir /var/lib/tor --shell /usr/sbin/nologin torproxy \
    && install -d -m 0700 -o torproxy -g torproxy /var/lib/tor \
    && install -d -o torproxy -g torproxy /var/log/privoxy

COPY --chmod=755 start.sh /usr/local/bin/start.sh
COPY --chmod=755 healthcheck.sh /usr/local/bin/healthcheck.sh
COPY privoxy.config.template /etc/privoxy/config.template
COPY torrc /etc/tor/torrc

USER torproxy

ENV TORPROXY_LISTEN_ADDRESS=0.0.0.0 \
    TORPROXY_LISTEN_PORT=8118

EXPOSE 8118

HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]
