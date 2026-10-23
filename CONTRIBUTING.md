# Contributing to torproxy

Thank you for your interest in contributing to `torproxy`! We welcome contributions that make the proxy simpler, more secure, and more reliable.

---

## Core Engineering Principles

Before contributing, please review our core project principles:

1. **NO BREAKING CHANGES**: We maintain strict backward compatibility. Existing Docker Compose files, environment variables, default port numbers (`8118`, `9050`, `8080`), legacy endpoints (`/status`, `/ip`, GET mutations), and JSON response shapes must remain functional without user migrations.
2. **Language Policy**: All code, comments, commit messages, documentation, tests, GitHub issues, and PRs must be written in **English**.
3. **Defense in Depth**: Container runs as non-root (UID != 0), Tor control is authenticated, and proxy fail-closed behavior must be maintained.
4. **Test-Driven Development (TDD)**: For bug fixes and behavior changes, write an automated test first, confirm it reproduces the issue, and then implement the solution. Maintain >= 85% test coverage.

---

## Development Setup

We recommend using [uv](https://docs.astral.sh/uv/) for reproducible development environment and dependency management:

```sh
# Clone the repository
git clone https://github.com/hapheus/torproxy.git
cd torproxy

# Install dependencies and sync virtual environment
uv sync --extra dev
```

### Running Tests Locally

```sh
# Run hermetic unit tests with coverage enforcement
uv run pytest tests/unit/ -v --cov=torproxy --cov-report=term-missing --cov-fail-under=85

# Run linter and static analysis
uv run ruff check .
uv run ruff format --check .
uv run mypy
shellcheck docker/start.sh docker/healthcheck.sh tests/integration/verify_container.sh
bash -n docker/start.sh docker/healthcheck.sh tests/integration/verify_container.sh
```

---

## Commit Guidelines (Conventional Commits)

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` Introduces a new backward-compatible feature or endpoint
- `fix:` Fixes a bug or vulnerability
- `docs:` Changes or additions to documentation
- `test:` Adds or modifies unit, integration, or smoke tests
- `refactor:` Code restructuring without changing external behavior
- `chore:` Dependency updates, tooling, or minor configuration

Example commit messages:
```text
feat(api): add additive /health diagnostic endpoint
fix(security): sanitize port environment variables in start.sh
test: add hermetic unit tests for tor control protocol parser
docs: clarify remote DNS resolution via socks5h in README
```

---

## Pull Request Checklist

When submitting a pull request, ensure that:

- [ ] All new and existing unit tests pass (`uv run pytest tests/unit/`).
- [ ] Code coverage across `src/torproxy` package is at least 85%.
- [ ] `uv run ruff check .` reports 0 errors.
- [ ] `uv run mypy` reports 0 type errors.
- [ ] `shellcheck` reports 0 warnings on all shell scripts.
- [ ] No breaking changes are introduced to public ports, APIs, or environment variables.
- [ ] Commits follow Conventional Commits formatting.
- [ ] Relevant documentation in `README.md` and `docs/` is updated.
