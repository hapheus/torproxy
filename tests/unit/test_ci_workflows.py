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


def test_daily_canary_reuses_the_shared_action() -> None:
    daily = _read("daily-image-verification.yml")
    assert "schedule:" in daily
    assert "uses: ./.github/actions/live-verification" in daily
    # The daily run verifies the published image, it must not rebuild it.
    assert 'build_local: "false"' in daily
    assert 'run_alerts: "true"' in daily
