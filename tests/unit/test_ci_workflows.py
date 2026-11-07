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
    pr_gate = WORKFLOWS / "pr-gate.yml"
    for line in pr_gate.read_text(encoding="utf-8").splitlines():
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
