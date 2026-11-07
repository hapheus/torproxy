"""ISSUE-18 (#82): the feature roadmap must list all three previews.

Hermetic documentation consistency test (precedent:
TestIssue13Gateway.test_gateway_readme_documents_forward_drop).
No application behavior is changed by this issue.
"""

import os

import pytest


@pytest.mark.unit
class TestRoadmapFeatures:
    def test_roadmap_lists_tls_ipv6_and_socks_auth(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "roadmap-features.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()

        # TLS termination (reverse-proxy strategy)
        assert "reverse proxy" in content.lower()
        # IPv6 listen addresses
        assert "::1" in content
        # SOCKS5 authentication for shared Docker networks
        assert "SOCKS5" in content
        # Threat assessment is mandatory for each entry
        assert content.count("Threat") >= 3
