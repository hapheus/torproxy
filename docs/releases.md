# Releases, Versioning, and Upgrade Guide

This document describes the release lifecycle, versioning contract, multi-architecture builds, upgrade testing, and rollback procedures for `torproxy`.

---

## 1. Versioning Contract

`torproxy` strictly adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/):

$$\text{MAJOR}.\text{MINOR}.\text{PATCH}$$

- **MAJOR**: Incompatible API or breaking behavioral changes.
  > [!IMPORTANT]
  > Under the project's absolute compatibility contract, breaking changes are strictly avoided. All core ports (8118, 9050, 8080), environment variables, REST endpoints, and legacy GET mutation routes remain backward-compatible across minor and patch releases.
- **MINOR**: Backward-compatible additive functionality, new endpoints (e.g., `/health`, `/diagnostics`, `/metrics`), new optional environment variables, or security hardening enhancements.
- **PATCH**: Backward-compatible bug fixes, dependency updates, and security patches.

---

## 2. Published Tags and Architecture Matrix

### Published Tags
Images are published to Docker Hub at [`hapheus/torproxy`](https://hub.docker.com/r/hapheus/torproxy):

| Tag | Mutability | Description |
| --- | ---------- | ----------- |
| `latest` | Mutable | Tracks the latest stable commit on the default branch (`main`). |
| `vX.Y.Z` (e.g. `v1.3.0`) | **Immutable** | Official, cryptographically tagged release pointing to an exact commit. Recommended for production deployments. |
| `vX.Y` (e.g. `v1.3`) | Mutable | Tracks the latest patch release within a minor release stream. |

### Supported CPU Architectures
Every official image build targets the following architectures using Docker Buildx:
- `linux/amd64` (Standard x86_64 servers and PCs)
- `linux/arm64` (Apple Silicon, AWS Graviton, Raspberry Pi 4/5 64-bit)
- `linux/arm/v7` (32-bit ARM devices, Raspberry Pi 2/3)

---

## 3. Supply Chain Security, SBOM, and Provenance

- **Provenance Attestations**: Published container images include SLSA provenance metadata (`mode=max`) embedded in the container manifest.
- **Software Bill of Materials (SBOM)**: Release builds include an SPDX/CycloneDX SBOM documenting all installed packages and file digests.
- **Automated Vulnerability Scanning**: Images are scanned against CVE databases (Trivy) on every PR and build before publishing.

---

## 4. Upgrade Guide

Because `torproxy` maintains an absolute compatibility contract, upgrades are 100% drop-in replacements. There are **zero configuration changes**, **zero database migrations**, and **zero secret reconfigurations** required.

### Upgrading via Docker Compose

1. Pull the new image version:
   ```bash
   docker compose pull
   ```
2. Re-create the container with zero manual intervention:
   ```bash
   docker compose up -d
   ```
3. Verify the upgraded container:
   ```bash
   # Check container status
   curl -s http://127.0.0.1:8080/status | jq .

   # Check health and diagnostics
   curl -s http://127.0.0.1:8080/health | jq .
   curl -s http://127.0.0.1:8080/diagnostics | jq .
   ```

---

## 5. Rollback Procedure

If an upgraded image exhibits unexpected behavior in your environment:

1. Pin your `docker-compose.yml` to the previously known-good version (e.g. `image: hapheus/torproxy:v1.1.1`):
   ```yaml
   services:
     torproxy:
       image: hapheus/torproxy:v1.1.1
   ```
2. Restart the service:
   ```bash
   docker compose up -d
   ```
3. Since `torproxy` is stateless and persists no internal database, the rollback is instantaneous and safe.

---

## 6. Release Verification Checklist

Maintainers must verify the following checklist before publishing any new version:
- [ ] All hermetic unit tests pass (`pytest tests/unit/ -v --cov=docker`).
- [ ] Static analysis passes (`ruff check .` and `shellcheck`).
- [ ] Container smoke and multi-port verification succeed (`tests/integration/verify_container.sh`).
- [ ] Backward compatibility upgrade test succeeds with unchanged Compose configuration.
- [ ] Documentation (`README.md`, `DOCKERHUB.md`, `docs/`) updated with the new version and features.
- [ ] Git tag created matching `vX.Y.Z` and pushed to GitHub.
