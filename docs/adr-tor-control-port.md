# ADR: Tor ControlPort connection strategy (ISSUE-08)

## Status
Accepted (one-shot stays).

## Context
Every API call opens a TCP connection to `127.0.0.1:9051`, reads the 32-byte
cookie, authenticates, issues one command and closes. A persistent,
authenticated client would save handshake overhead under load (32 workers),
but introduces reconnect races, stale-socket handling and lock-ordering
complexity in a threaded server where locks must never be held during
network I/O (`AGENTS.md`). The current one-shot client is stateless and
safe, at the cost of one handshake per command (`/status` = 2 handshakes).

## Decision
Keep the one-shot, authenticated-per-command client. It is simple, correctly
serialized by design (no shared socket), and its overhead is negligible
compared to Tor bootstrap/egress latencies. A persistent client may be
revisited if profiling shows handshake cost dominates.

In parallel, `send_command` now maps all socket/protocol failures to the
stable, leak-free error `Tor control unavailable` — raw socket text
(`[Errno ...]`, paths) is never returned to API clients.
