"""ISSUE-12 (#76): egress probe must distinguish failure causes.

Previously every transport failure collapsed into
"egress check service unreachable", so a dead local HTTP proxy
(Privoxy, 8118), a Tor upstream failure (proxy answers 5xx) and a
dead check service were indistinguishable.

These hermetic tests pin the stable, operator-safe error strings
for each cause. Raw socket text must never leak into the error.
"""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from torproxy.adapters.probes import TorEgressProbe


def _probe() -> TorEgressProbe:
    return TorEgressProbe(8118, max_retries=0, circuit_threshold=100)


@pytest.mark.unit
class TestProbeDiagnosis:
    def test_local_proxy_connection_refused(self):
        probe = _probe()
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.URLError(
                ConnectionRefusedError(111, "Connection refused")
            )
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert err == "local HTTP proxy unreachable"
        assert "111" not in err and "refused" not in err.lower()

    def test_proxy_5xx_is_tor_upstream_failure(self):
        probe = _probe()
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.HTTPError(
                "https://check.torproject.org/api/ip", 503, "Service Unavailable", {}, None
            )
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert err == "Tor upstream unavailable via local HTTP proxy (HTTP 503)"

    def test_proxy_4xx_is_check_service_answer(self):
        # A 4xx through a healthy proxy proves the check service
        # itself answered (e.g. rate-limited), not a Tor upstream
        # failure. Only 5xx from the proxy means upstream failure.
        probe = _probe()
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.HTTPError(
                "https://check.torproject.org/api/ip", 429, "Too Many Requests", {}, None
            )
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert err == "egress check service returned HTTP 429"

    def test_circuit_open_keeps_last_cause(self):
        # After repeated local-proxy failures trip the breaker,
        # the open-circuit error must keep the original cause
        # instead of reverting to "check service unreachable".
        probe = TorEgressProbe(8118, max_retries=0, circuit_threshold=2, circuit_cooldown=60)
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.URLError(
                ConnectionRefusedError(111, "Connection refused")
            )
            m.return_value = opener
            probe.resolve()
            probe.resolve()
            ip, err = probe.resolve()

        assert ip is None
        assert "local HTTP proxy unreachable" in err
        assert "circuit" in err

    def test_check_service_timeout(self):
        probe = _probe()
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.URLError(TimeoutError("timed out"))
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert err == "egress check service unreachable"

    def test_generic_url_error_stays_check_service(self):
        # Backwards compat: ISSUE-06 circuit-breaker test raises
        # URLError("down") and expects an "unreachable" reason.
        probe = _probe()
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.side_effect = urllib.error.URLError("down")
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert "unreachable" in err

    def test_is_tor_false_is_not_retried_and_not_transport(self):
        probe = _probe()
        resp = MagicMock()
        resp.read.return_value = b'{"IP": "203.0.113.7", "IsTor": false}'
        with patch("urllib.request.build_opener") as m:
            opener = MagicMock()
            opener.open.return_value = resp
            m.return_value = opener
            ip, err = probe.resolve()

        assert ip is None
        assert "IsTor=false" in err
        # Definitive answer from the check service: exactly one attempt.
        assert opener.open.call_count == 1
