# Quality Baseline (Milestone 0)

This document establishes the reproducible, empirical quality baseline for `torproxy` as of October 2026, measured prior to Milestone 1 improvements.

## 1. Measurement Environment

- **Date:** 2026-10-18
- **Operating System:** macOS Darwin (arm64 / Apple Silicon)
- **Python Version:** 3.14.7 (devenv virtualenv)
- **Pytest Version:** 9.1.1
- **Coverage Plugin:** pytest-cov 7.1.0 / Coverage.py 7.16.2
- **Ruff Version:** 0.6.9
- **ShellCheck Version:** 0.10.0
- **Docker CLI Version:** 29.9.1 (desktop-linux client; local daemon was not running during offline test capture)

---

## 2. Test Execution & Code Coverage

### Unit and Contract Test Suite
- **Command:**
  ```sh
  pytest tests/unit/ --cov=api --cov-report=term-missing
  ```
- **Results:**
  - **Total Tests:** 62 tests collected, 62 passed, 0 failed, 0 skipped.
  - **Execution Time:** ~1.18 seconds.
- **Coverage Summary:**
  ```text
  Name            Stmts   Miss  Cover   Missing
  ---------------------------------------------
  docker/api.py     124      1    99%   206
  ---------------------------------------------
  TOTAL             124      1    99%
  ```
  *(Note: The sole uncovered line in `docker/api.py` is line 206 `if __name__ == '__main__': run()`)*.

---

## 3. Static Analysis & Syntax Verification

| Check | Target | Command | Result |
|---|---|---|---|
| **Python Linter** | Entire repository | `ruff check .` | Passed (0 errors) |
| **Shell Syntax** | `docker/start.sh`, `docker/healthcheck.sh` | `bash -n docker/*.sh` | Passed |
| **ShellCheck** | `docker/start.sh`, `docker/healthcheck.sh` | `shellcheck docker/*.sh` | Passed (0 issues) |
| **Compose Schema (Root)** | `docker-compose.yml` | `docker compose config` | Valid (0 errors) |
| **Compose Schema (Browserless)** | `examples/browserless-chromium-via-tor/docker-compose.yml` | `docker compose config` | Valid (Notice: exposes 8080 to host) |
| **Compose Schema (CRW)** | `examples/crw-web-scraper-via-tor/docker-compose.yml` | `docker compose config` | Valid |
| **Compose Schema (SearXNG)** | `examples/searxng-via-tor/docker-compose.yml` | `docker compose config` | Valid |

---

## 4. Docker & Runtime Characteristics

The following metrics are derived from repository definitions and CI canary runs:

- **Base Image:** `debian:bookworm-slim`
- **Architectures Supported:** `linux/amd64`, `linux/arm64` (built via GitHub Actions buildx)
- **Process Model:** `tini` (PID 1) supervising non-root user `torproxy`, spawning:
  - `tor -f /tmp/torrc`
  - `privoxy --no-daemon /tmp/privoxy.config`
  - `python3 /usr/local/bin/api.py`
- **Docker Healthcheck Configuration:**
  - Interval: 30s
  - Timeout: 15s
  - Start period: 180s (accommodates Tor network directory bootstrap)
  - Retries: 3
- **Unmeasured Values (Local Run):**
  - *Local Docker Image Size & Cold-Start Latency:* The local Docker daemon was inactive during this baseline collection. Live image size and runtime bootstrap benchmarks are monitored continuously in GitHub Actions canary workflows (`.github/workflows/daily-image-verification.yml`).

---

## 5. Security & Correctness Baseline Findings (Addressed in M1)

The baseline inspection identified the following areas prioritized for Milestone 1:

1. **Host API Publication in Example:** `examples/browserless-chromium-via-tor/docker-compose.yml` binds `8080:8080` to all host interfaces (`0.0.0.0`), conflicting with documentation.
2. **Tor Control Parsing:** `docker/api.py` uses single `recv(1024)` calls and does not parse 4xx/5xx reply codes on commands such as `SETCONF` or `SIGNAL`.
3. **Control Port Authentication:** `docker/torrc` sets `CookieAuthentication 0` (unauthenticated ControlPort).
4. **Egress Verification:** `get_current_ip()` in `docker/api.py` checks for the presence of an `IP` field but does not assert `IsTor: true`.
5. **Configuration Input Validation:** `validate_configuration()` in `docker/start.sh` uses `^[0-9.]+$` for IP validation.
