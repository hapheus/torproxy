# Changelog

All notable changes to `torproxy` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [2.7.0] — 2026-11-10

### Added
- **mcp**: Add validated Model Context Protocol Registry manifest (`server.json`) under namespace `io.github.hapheus/torproxy` (#132)
- **contracts**: Enforce version synchronization between `server.json`, `pyproject.toml`, and Docker container labels (#132)

## [2.6.2] — 2026-11-10

### Fixed
- **ci**: Harden live image verification composite action with retry loops, backoff, and fallback IP verification for MCP (`torproxy_fetch`) and transparent gateway egress (#127, #128, #129)
- **ci**: Accept Tor bootstrap completion via `/health` (`progress == 100`) during GeoIP test container validation and dump container logs on failure (#128, #129)
- **gateway**: Support fallback IP reflection check with host IP leak detection in `verify_gateway.sh` (#127, #129)

## [2.6.1] — 2026-11-10

### Fixed
- **docker**: Install `/usr/local/bin/torproxy` CLI entrypoint in container image so `docker exec -i torproxy torproxy mcp` works as documented (#124, #125)
- **mcp**: Support MCP Streamable HTTP (`POST /mcp`, `POST /sse`, `POST /`), preserve query-token SSE session authentication, use `hmac.compare_digest`, and bind `AF_INET6` for IPv6 addresses (#124, #125)
- **gateway**: Exempt MCP port `2501` in transparent gateway netfilter rules (#124, #125)
- **mcp**: Negotiate `protocolVersion`, support `prompts/list` and `resources/templates/list`, accept `strict_nodes` alias, and block non-HTTP(S) redirects in `torproxy_fetch` (#124, #125)

## [2.6.0] — 2026-11-10

### Added
- **mcp**: Integrated Model Context Protocol (MCP) server on port 2501 and Stdio transport (ISSUE-122, #123)
- **mcp**: Zero-config `torproxy_fetch` tool for leak-free HTTP/HTTPS and `.onion` fetches
- **canary**: Add live MCP server and `torproxy_fetch` verification to canary and container tests

## [2.1.1] — 2026-11-07

### Fixed
- **docker**: Pin image Python to 3.14 and install into sysconfig purelib instead of dist-packages (ISSUE-15, #79, #98; original approach contributed by @Joffy-Maria in #93)

### CI
- **ci**: Extend hermetic unit-test matrix to Python 3.10/3.11/3.14 and verify image import in docker-smoke (ISSUE-15, #79, #98)

## [2.1.0] — 2026-11-06

Sprint 2 gateway security architecture release.

### Fixed
- **gateway**: Remove unrestricted ESTABLISHED accept from kill switch (ISSUE-02, #89)
- **gateway**: Scope WAN bypass to dedicated tor user via privilege-dropping init (ISSUE-03, #91)
- **gateway**: Make setup_gateway idempotent via -C probes (ISSUE-05, #92)

### CI
- **gateway**: Wait for API in hardened smoke step before verifying
- **gateway**: Allow SETUID/SETGID in hardened test and fix cookie perms under cap-drop
- **gateway**: Verify unprivileged daemons instead of container UID

### Chore
- **release**: Bump version to 2.1.0 and add Sprint 2 release notes (#94)

## [2.0.2] — 2026-11-06

Sprint 1 security & contract correctness release.

### Fixed
- **version**: Derive __version__ from pyproject.toml (single source of truth) (ISSUE-07, #85)
- **config**: Make TORPROXY_STRICT_NODES default strictly False (ISSUE-04, #84)
- **web**: Reject cross-origin mutations with 403 and restrict wildcard CORS (ISSUE-01, #83)

### Chore
- **release**: Update uv.lock for version 2.0.2
- **release**: Bump version to 2.0.2 and add Sprint 1 release notes
- **hygiene**: Ignore .mypy_cache and guard compiled artifacts in contract tests (ISSUE-16, #86)

## [2.0.1] — 2026-11-06

### Added
- **gateway**: Add compose pull policy, gateway observability and bump to v2.0.1 (#64)

## [2.0.0] — 2026-11-06

### Added
- **gateway**: Transparent Tor gateway for Docker and bump to v2.0.0 (#62)

## [1.7.1] — 2026-11-03

### CI
- **deps**: Bump astral-sh/setup-uv (#61)

### Chore
- **deps**: Bump the python-dependencies group with 3 updates (#60)

## [1.7.0] — 2026-10-31

### Added
- **api**: Add optional management API authentication and security hardening (#56) (#57)

### Documentation
- **security**: Refer neutrally to pinned Alpine Linux base image (#54) (#55)

### Chore
- **release**: Bump package and container version to 1.7.0 (#58) (#59)

## [1.6.1] — 2026-10-27

### Refactored
- **docker**: Remove historical shims and modernize daemon entrypoint (#53)

### CI
- **deps**: Bump the github-actions group with 6 updates (#50)

## [1.6.0] — 2026-10-26

### CI
- Restrict top-level workflow token permissions (closes #43) (#44)

### Chore
- **release**: Bump package and container version to 1.6.0 (#51) (#52)
- Add kuenstlichedummheit-sys and majorungustl to CODEOWNERS (#48) (#49)
- **deps**: Bump alpine (#47)
- **deps**: Set dependabot update schedule to tuesday (#45) (#46)

## [1.5.0] — 2026-10-23

### Added
- **cli**: Add --version and --help flags to runtime entrypoint (#42)
- **examples**: Add macOS Chrome incognito terminal example via torproxy (#41)

## [1.4.1] — 2026-10-23

### Performance
- **docker**: Minimize image size by migrating to alpine 3.21 (#37) (#38)

### Documentation
- Align CONTRIBUTING.md test and tooling instructions with uv and src/torproxy (#36)
- Add OpenSSF Best Practices badge to README (#35)

### CI
- **security**: Pin dependencies with uv.lock and setup-uv in workflows (#34)
- **scorecard**: Pin base image by SHA and replace curl installer with containerized trivy (#33)
- **scorecard**: Pin all action dependencies by SHA and introduce fuzzing harness (#32)
- **deps**: Bump the github-actions group with 13 updates (#31)

## [1.4.0] — 2026-10-23

### Added
- **architecture**: Decouple core proxy into SOLID package and align security scanners (#30)

### Documentation
- Clean up internal milestone and audit references for open source release (#29)

## [1.3.0] — 2026-10-18

### Added
- **country**: Support static and dynamic country-specific exit nodes (#28)

## [1.2.0] — 2026-10-18

### Added
- **supply-chain**: Implement predictable releases, automated scanning, SBOM provenance, and hardened runtime (Milestone 7) (#25)
- **observability**: Add diagnostics and prometheus metrics endpoints with privacy safeguards (M6) (#23)
- **test**: Comprehensive testing and CI enhancements (Milestone 3) (#17)
- **lifecycle**: Implement thread-safe caching, SOCKS5 probe, and signal handling (#14) (#15)

### Fixed
- **security**: Resolve critical correctness, control authentication, and exposure issues (#12) (#13)

### Documentation
- Add Quality Gate 10/10 audit report and link in README (Milestone 8) (#26)
- Overhaul README and add security policy, contributing guide, and templates (M5) (#21)
- **m0**: Establish baseline and contract test suite (#10) (#11)

### Testing
- Add automated compose and examples integrity validation suite (M4) (#19)

## [1.1.1] — 2026-10-11

### Fixed
- **canary**: Harden live image verification against exit node flapping (#8)

### Chore
- **devenv**: Lock inputs and configure git-hooks

## [1.1.0] — 2026-10-10

### Added
- **ci**: Add PR gate, daily live canary verification, and fix SOCKS port (#5)
- Add CRW and SearXNG Tor examples
- Add Browserless Tor proxy example

### Fixed
- **docker**: Authenticate Docker Hub before setup actions and chain canary verification (#6)
- Give Tor more time to bootstrap before the healthcheck fails.

## [1.0.0] — 2026-07-28

### Added
- Add SOCKS5 proxy access
- Improve Tor proxy control API
- Add RESTful control API and document proxy usage
- Establish torproxy project

### Fixed
- Generate Docker tag for main publishes

### Documentation
- Clarify Docker Tor proxy positioning

---

[Unreleased]: https://github.com/hapheus/torproxy/compare/v2.7.0...HEAD
[2.7.0]: https://github.com/hapheus/torproxy/compare/v2.6.2...v2.7.0
[2.6.2]: https://github.com/hapheus/torproxy/compare/v2.6.1...v2.6.2
[2.6.1]: https://github.com/hapheus/torproxy/compare/v2.6.0...v2.6.1
[2.6.0]: https://github.com/hapheus/torproxy/compare/v2.5.0...v2.6.0
[2.1.1]: https://github.com/hapheus/torproxy/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/hapheus/torproxy/compare/v2.0.2...v2.1.0
[2.0.2]: https://github.com/hapheus/torproxy/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/hapheus/torproxy/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/hapheus/torproxy/compare/v1.7.1...v2.0.0
[1.7.1]: https://github.com/hapheus/torproxy/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/hapheus/torproxy/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/hapheus/torproxy/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/hapheus/torproxy/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/hapheus/torproxy/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/hapheus/torproxy/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/hapheus/torproxy/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/hapheus/torproxy/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/hapheus/torproxy/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/hapheus/torproxy/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/hapheus/torproxy/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/hapheus/torproxy/releases/tag/v1.0.0
