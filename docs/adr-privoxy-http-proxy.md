# ADR: HTTP proxy daemon — keep Privoxy for now (ISSUE-12, #76)

## Status

Accepted: keep Privoxy on port 8118. This ADR records the evaluation;
it does not schedule a replacement. The probe-diagnosis part of
ISSUE-12 is implemented separately (see `TorEgressProbe`).

## Context

Privoxy (`docker/privoxy.config.template`, `forward-socks5t`) is the
HTTP/HTTPS forward proxy on the guaranteed port 8118
(`docs/compatibility.md`). It is only used as a forwarder: its
filtering features are unused, its config is two functional lines,
and SOCKS-only clients already have a direct path via Tor SOCKS5 on
9050. Candidates for replacing it were Tor's `HTTPTunnelPort` and
`tinyproxy`.

## Evaluation

| Criterion | Privoxy (current) | `HTTPTunnelPort` | `tinyproxy` |
|---|---|---|---|
| Plain HTTP (absolute URI) | Yes | Unverified — CONNECT-centric | Yes |
| HTTPS CONNECT | Yes | Yes (core use case) | Yes |
| Remote DNS via SOCKS (`forward-socks5t`-equivalent, no leak) | Yes (trailing dot) | Unverified | Requires explicit config |
| Fail-closed if Tor is down | Yes (`wait -n` in `start.sh` kills the container) | Unverified | Unverified |
| IPv6 | Yes | Unverified | Config-dependent |
| Attack surface | Extra C daemon; minimal config, non-root, `cap_drop: [ALL]`, pinned Alpine, Trivy-scanned | Part of Tor itself: smallest surface | Extra C daemon, similar profile to Privoxy |
| Compatibility (8118, protocol, env vars) | Guaranteed contract | Would need a full prototype on all criteria above first | Same prototype requirement |

No candidate has been shown to meet all criteria without a prototype
against plain HTTP, CONNECT, DNS-leak and fail-closed tests, and the
compatibility contract (`docs/compatibility.md`) requires port 8118
and default behavior to stay stable within the 2.x stream. A
replacement without that prototype would risk the main use case
(`curl -x http://127.0.0.1:8118 https://check.torproject.org/api/ip`,
see `docs/api.md`) for a hypothetical hardening gain.

## Decision

Keep Privoxy. Revisit only if a prototype for a candidate passes,
at minimum: plain HTTP, HTTPS CONNECT, remote-DNS leak test,
fail-closed test with Tor stopped, IPv6, and the contract suite in
`tests/unit/test_contracts.py` — and a CVE/supply-chain comparison
shows a concrete, measured advantage.

In parallel, the egress-probe diagnosis no longer conflates a dead
local HTTP proxy, a Tor upstream failure (proxy 5xx) and an
unreachable check service (`_classify_transport_error` in
`src/torproxy/adapters/probes.py`, pinned by
`tests/unit/test_probe_diagnosis.py`). A SOCKS5-native probe path
was deliberately not added: `urllib` has no SOCKS support, which
would require a new dependency (`PySocks`) or a hand-rolled
SOCKS5+TLS handshake.
