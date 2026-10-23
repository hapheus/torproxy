FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8

LABEL org.opencontainers.image.title="torproxy" \
      org.opencontainers.image.description="A minimal HTTP proxy routed through Tor" \
      org.opencontainers.image.version="1.4.0" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/hapheus/torproxy" \
      org.opencontainers.image.url="https://github.com/hapheus/torproxy"

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl privoxy tini tor tor-geoipdb python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --home-dir /var/lib/tor --shell /usr/sbin/nologin torproxy \
    && install -d -m 0700 -o torproxy -g torproxy /var/lib/tor \
    && install -d -o torproxy -g torproxy /var/log/privoxy

COPY src/torproxy /usr/lib/python3/dist-packages/torproxy
COPY --chmod=755 docker/start.sh /usr/local/bin/start.sh
COPY --chmod=755 docker/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY --chmod=755 docker/api.py docker/tor_control.py /usr/local/bin/
COPY docker/privoxy.config.template /etc/privoxy/config.template
COPY docker/torrc /etc/tor/torrc

USER torproxy

ENV TORPROXY_LISTEN_ADDRESS=0.0.0.0 \
    TORPROXY_LISTEN_PORT=8118 \
    TORPROXY_API_PORT=8080 \
    TORPROXY_SOCKS_PORT=9050

EXPOSE 8118 8080 9050

HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
  CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]
