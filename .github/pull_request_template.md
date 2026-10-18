### Description
<!-- Provide a concise description of what this PR does and why it is needed. -->

### Related Issues
<!-- Link related issues, e.g., Closes #123 -->

### Type of Change
- [ ] `feat`: Backward-compatible new feature or additive API
- [ ] `fix`: Bug fix
- [ ] `docs`: Documentation improvement
- [ ] `test`: Unit, integration, or smoke tests
- [ ] `refactor`: Internal code refactoring
- [ ] `chore`: Tooling, dependencies, or maintenance

### Compatibility Contract Checklist (NO BREAKING CHANGES)
- [ ] Existing ports (`8118`, `9050`, `8080`) are preserved with their defaults
- [ ] Existing environment variables and defaults remain functional
- [ ] Existing REST API endpoints (`/status`, `/ip`, GET mutations) remain functional
- [ ] Response JSON schemas are preserved (only additive fields allowed)
- [ ] Standard `docker compose up -d` works without configuration migration

### Quality Checklist
- [ ] Hermetic unit tests added/updated (`pytest tests/unit/`)
- [ ] Test coverage is >= 90%
- [ ] Static analysis passes (`ruff check .`, `shellcheck`)
- [ ] Documentation updated (`README.md`, `docs/`)
- [ ] Conventional Commit messages used
