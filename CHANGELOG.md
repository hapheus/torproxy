# Changelog

All notable changes to `torproxy` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed
- **gateway**: Scope WAN bypass to dedicated tor user via privilege-dropping init
- **gateway**: Remove unrestricted ESTABLISHED accept from kill switch

### CI
- **gateway**: Wait for API in hardened smoke step before verifying
- **gateway**: Allow SETUID/SETGID in hardened test and fix cookie perms under cap-drop
- **gateway**: Verify unprivileged daemons instead of container UID

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

[Unreleased]: https://github.com/hapheus/torproxy/compare/v2.0.2...HEAD
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
