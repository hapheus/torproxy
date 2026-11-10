"""Structural guards for CI workflow polling loops (ISSUE-19).

The PR gate's Docker smoke job used unbounded ``curl`` calls while
waiting for services to come up. In gateway mode a single attempt can
block until the OS TCP timeout (~127s), turning a nominal 60s wait
into ~28 minutes. These tests keep every workflow HTTP poll bounded.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _curl_http_lines() -> list[str]:
    lines: list[str] = []
    paths = [
        WORKFLOWS / "pr-gate.yml",
        WORKFLOWS.parents[1] / ".github" / "actions" / "live-verification" / "action.yml",
    ]
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "curl" in line and "http" in line:
                lines.append(line)
    return lines


def test_every_workflow_curl_poll_has_a_max_time() -> None:
    unbounded = [line.strip() for line in _curl_http_lines() if "--max-time" not in line]
    assert unbounded == [], f"unbounded curl polls in workflows: {unbounded}"


def test_gateway_bootstrap_is_polled_inside_the_container() -> None:
    pr_gate = (WORKFLOWS / "pr-gate.yml").read_text(encoding="utf-8")
    # Polling via the published host port goes through the gateway kill
    # switch; polling over loopback inside the container does not.
    assert "docker exec torproxy-gateway-smoke curl" in pr_gate
    assert "curl -s http://127.0.0.1:8085/status" not in pr_gate


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_live_verification_is_a_composite_action() -> None:
    # ISSUE-117: the live check must run before publish/release, not
    # only after it (daily workflow_run). A composite action lets the
    # PR gate, publish, release and daily canary share one
    # implementation. (A reusable workflow was tried first, but
    # relative reusable paths fail with startup_failure on
    # pull_request events — GitHub resolves them against the merge
    # commit — so the composite action is the reliable form.)
    live = (
        WORKFLOWS.parents[1] / ".github" / "actions" / "live-verification" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "using: composite" in live
    assert "Verify GeoIP Database Availability & Auto-Update" in live
    # Upstream drift guard: HEAD sizes must fit the configured limits.
    assert "Content-Length" in live
    assert "geoip6_max_bytes" in live


def test_composite_action_respects_composite_constraints() -> None:
    # Composite actions require shell: bash on run steps, cannot use
    # the secrets context (token must be passed as an input) and do
    # not support timeout-minutes on steps.
    live = (
        WORKFLOWS.parents[1] / ".github" / "actions" / "live-verification" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "secrets." not in live
    assert "timeout-minutes" not in live
    assert live.count("run: |") == live.count("shell: bash")


def test_gateway_bootstrap_is_polled_inside_the_container_in_live_action() -> None:
    # ISSUE-19 regression (PR #118): polling the gateway container
    # via its published host port goes through the kill switch and
    # never returns "connected" — the step burned ~9 minutes although
    # Tor bootstrapped in seconds. Poll over loopback in-container.
    live = (
        WORKFLOWS.parents[1] / ".github" / "actions" / "live-verification" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "docker exec torproxy-canary-gateway curl" in live
    assert "http://localhost:8089/status" not in live
    # Bootstrap waits must use Tor progress (100%), not /status
    # "connected", which additionally depends on the external
    # check.torproject.org egress probe (PR #121 flake).
    assert ".tor.progress" in live
    assert (
        "8080/status"
        not in live.split("Verify Transparent Tor Gateway Mode")[1].split(
            "Verify GeoIP Upstream Size Drift Guard"
        )[0]
    )


def test_pr_gate_runs_live_verification_before_merge() -> None:
    pr_gate = _read("pr-gate.yml")
    assert "live-image-verification" in pr_gate
    assert "uses: ./.github/actions/live-verification" in pr_gate


def test_publish_waits_for_live_verification() -> None:
    publish = _read("publish-dockerhub.yml")
    assert "uses: ./.github/actions/live-verification" in publish
    assert "needs: verify-live" in publish or "needs: [verify-live]" in publish


def test_release_waits_for_live_verification() -> None:
    release = _read("release.yml")
    assert "uses: ./.github/actions/live-verification" in release
    assert "verify-live" in release


def test_publish_mcp_waits_for_live_verification() -> None:
    publish_mcp = _read("publish-mcp.yml")
    assert "uses: ./.github/actions/live-verification" in publish_mcp
    assert "needs: verify-live" in publish_mcp or "needs: [verify-live]" in publish_mcp
    assert "id-token: write" in publish_mcp
    assert "mcp-publisher login github-oidc" in publish_mcp
    assert "docker manifest inspect" in publish_mcp
    publish_dockerhub = _read("publish-dockerhub.yml")
    assert "io.modelcontextprotocol.server.name=io.github.hapheus/torproxy" in publish_dockerhub


def test_daily_canary_reuses_the_shared_action() -> None:
    daily = _read("daily-image-verification.yml")
    assert "schedule:" in daily
    assert "uses: ./.github/actions/live-verification" in daily
    # The daily run verifies the published image, it must not rebuild it.
    assert 'build_local: "false"' in daily
    assert 'run_alerts: "true"' in daily
