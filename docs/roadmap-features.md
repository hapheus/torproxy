# Feature Roadmap (ISSUE-18, #82)

This document records three product features as roadmap entries.
None of them is a bug fix and none is implemented yet: defaults,
ports and JSON shapes stay exactly as guaranteed in
`docs/compatibility.md`. Each entry carries a threat assessment
and points to its own follow-up issue.

## 1. TLS termination for the management API

**Status:** Not implemented. The API (`src/torproxy/web/server.py`)
is plain HTTP; `SECURITY.md`, `DOCKERHUB.md` and
`docs/configuration.md` already require an authenticating reverse
proxy (Caddy, Nginx or Traefik with HTTP Basic Auth / OAuth / mTLS)
whenever port 8080 leaves loopback.

**Threat:** `TORPROXY_API_TOKEN` and control mutations travel in
cleartext if the API is exposed across a network without TLS, and
a token can be replayed by anyone able to observe the traffic.
Today this is mitigated only by binding to `127.0.0.1` and by
operator discipline.

**Recommended approach:** Keep the container HTTP-only and
terminate TLS in the reverse proxy (no certificate management in
the container, no new dependency). The follow-up issue should add
a documented, tested reverse-proxy example (e.g. Caddy) under
`examples/` instead of native TLS support in `ProxyHTTPServer`.

**Compatibility:** No change to the container endpoint. Additive
documentation only.

**Effort / open decisions:** Small (docs + example). Open: which
reverse proxy to ship as the reference example.

**Follow-up issue:** #106 (TLS).

## 2. IPv6 listen addresses

**Status:** Not implemented. `TORPROXY_LISTEN_ADDRESS` and
`TORPROXY_API_LISTEN_ADDRESS` are validated as IPv4 only
(`ipaddress.IPv4Address` in `src/torproxy/configuration.py`) and
`ProxyHTTPServer` binds an `AF_INET` socket. Tor itself may
bootstrap over IPv6 (scoped exception); every other process stays
IPv4-only, so no IPv6 clearnet leak is possible (`README.md`).

**Threat:** The risk is a future misconfiguration rather than a
current exposure: if `::` were accepted without the same
loopback-only binding discipline as `0.0.0.0`, an operator could
accidentally publish the unauthenticated API or proxies on a
public IPv6 interface. IPv6 must therefore ship with the same
`127.0.0.1`-default and explicit warning as IPv4.

**Recommended approach:** Relax validation to
`ipaddress.ip_address()` and add an `AF_INET6` server variant
behind the same settings; keep the defaults (`0.0.0.0`) unchanged
so existing deployments are unaffected.

**Compatibility:** Additive: `::1`/`::` become valid values,
existing IPv4 values keep working.

**Effort / open decisions:** Medium (validation, socket family,
tests on IPv6-capable hosts, docs). Open: dual-stack (`::` with
v4-mapped) vs. separate v4/v6 sockets.

**Follow-up issue:** #107 (IPv6).

## 3. SOCKS5 username/password authentication

**Status:** Not implemented. Tor's `SocksPort` (`docker/torrc`)
accepts unauthenticated connections; `docs/compatibility.md`
documents SOCKS5 on 9050 as "Unauthenticated". The compose
templates bind it to `127.0.0.1` on the host.

**Threat:** In shared Docker networks, any container that can
reach `torproxy:9050` can use the proxy without credentials —
abuse, traffic attribution to the operator's Tor exits, and
uncontrolled egress. Tor's control port is not affected (separate,
cookie-authenticated, loopback-only). The threat is therefore
network-local, not internet-facing, as long as host binding stays
on loopback.

**Recommended approach:** Add an optional, additive pair of
environment variables (e.g. `TORPROXY_SOCKS_USER` /
`TORPROXY_SOCKS_PASSWORD`, documented with placeholders in
`.env.example` only) rendered into `SocksPort` authentication in
`docker/torrc`; the default stays no-auth so existing clients
keep working. Secrets must never be logged or committed.

**Compatibility:** Additive: no env vars set means exactly the
current behavior.

**Effort / open decisions:** Medium (config rendering, secret
handling, SOCKS5 handshake tests, docs). Open: which Tor
`SocksPort` auth mechanism to use and how rotation/revocation
should work.

**Follow-up issue:** #108 (SOCKS5 auth).
