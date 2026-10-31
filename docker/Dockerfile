FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

LABEL org.opencontainers.image.title="torproxy" \
      org.opencontainers.image.description="A minimal HTTP proxy routed through Tor" \
      org.opencontainers.image.version="1.7.0" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/hapheus/torproxy" \
      org.opencontainers.image.url="https://github.com/hapheus/torproxy"

RUN apk add --no-cache bash ca-certificates curl privoxy tini tor python3 \
    && addgroup -S torproxy \
    && adduser -S -h /var/lib/tor -s /sbin/nologin -G torproxy torproxy \
    && addgroup torproxy privoxy \
    && install -d -m 0755 -o torproxy -g torproxy /etc/privoxy \
    && install -d -m 0700 -o torproxy -g torproxy /var/lib/tor \
    && install -d -o torproxy -g torproxy /var/log/privoxy \
    && ln -sf /sbin/tini /usr/bin/tini

ENV PYTHONPATH=/usr/lib/python3/dist-packages \
    TORPROXY_LISTEN_ADDRESS=0.0.0.0 \
    TORPROXY_LISTEN_PORT=8118 \
    TORPROXY_API_PORT=8080 \
    TORPROXY_SOCKS_PORT=9050

COPY src/torproxy /usr/lib/python3/dist-packages/torproxy
COPY --chmod=755 docker/start.sh /usr/local/bin/start.sh
COPY --chmod=755 docker/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY --chmod=644 docker/privoxy.config.template /etc/privoxy/config.template
COPY --chmod=644 docker/torrc /etc/tor/torrc

USER torproxy

EXPOSE 8118 8080 9050

HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]
