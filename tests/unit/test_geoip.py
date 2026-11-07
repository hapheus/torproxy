"""Unit tests for optional periodic GeoIP auto-update (ISSUE-20).

Hermetic: no real network access. Downloads are faked via a stub fetcher.
"""

from __future__ import annotations

import pytest

from torproxy.configuration import Settings, render_torrc
from torproxy.runtime.geoip import (
    _https_fetch,
    _sighup_tor,
    has_valid_geoip,
    main,
    run_loop,
    update_geoip,
    validate_geoip_content,
)

GEOIP_V4 = b"# Last updated based on Test\n16777216,16777471,DE\n16777472,16777727,AT\n"
GEOIP_V6 = b"# Last updated based on Test\n2001:db8::,2001:db8:ffff:ffff:ffff:ffff:ffff:ffff,DE\n"


def _fetcher(pages: dict[str, bytes] | None = None, error: Exception | None = None):
    def fetch(url: str, max_bytes: int) -> bytes:
        if error is not None:
            raise error
        assert pages is not None
        return pages[url]

    return fetch


class TestGeoipUserAgent:
    def test_fetch_uses_default_urllib_user_agent(self, monkeypatch):
        # ISSUE-20 regression (#113): GitLab serves raw files only
        # to known User-Agent patterns (curl/*, Python-urllib/*,
        # browsers). A custom "torproxy-geoip/1" UA gets HTTP 403,
        # so the downloader must not set a custom User-Agent.
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n):
                return GEOIP_V4

        def fake_urlopen(request, timeout=None):
            captured["ua"] = request.get_header("User-agent")
            return FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        data = _https_fetch("https://gitlab.torproject.org/x/geoip", 1024)
        assert data == GEOIP_V4
        assert captured["ua"] is None  # urllib default (Python-urllib/*)


class TestGeoipSettings:
    def test_defaults_are_disabled_and_backward_compatible(self):
        s = Settings.from_mapping({})
        assert s.geoip_auto_update is False
        assert s.geoip_update_interval == 86400
        assert s.geoip_dir == "/var/lib/tor/geoip"
        assert s.geoip_url.startswith("https://gitlab.torproject.org/")
        assert s.geoip6_url.startswith("https://gitlab.torproject.org/")
        assert s.geoip_max_bytes == 16 * 1024 * 1024
        assert s.geoip6_max_bytes == 32 * 1024 * 1024

    def test_defaults_cover_current_upstream_sizes_with_headroom(self):
        # Regression ISSUE-117 (#116): the single 10 MiB limit could
        # never accept the IPv6 upstream file (~16 MB), so the
        # auto-update silently fell back to the bundled DB forever
        # while the canary asserted a download inside the container.
        # Recorded 2026-11-07 via HEAD on the default URLs.
        upstream_v4_bytes = 9_855_249
        upstream_v6_bytes = 16_075_127
        s = Settings.from_mapping({})
        assert s.geoip_max_bytes > upstream_v4_bytes
        assert s.geoip6_max_bytes > upstream_v6_bytes

    def test_legacy_single_limit_applies_to_both_files(self):
        s = Settings.from_mapping({"TORPROXY_GEOIP_MAX_BYTES": "12345"})
        assert s.geoip_max_bytes == 12345
        assert s.geoip6_max_bytes == 12345

    def test_ipv6_limit_overrides_legacy_limit(self):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_MAX_BYTES": "12345", "TORPROXY_GEOIP6_MAX_BYTES": "67890"}
        )
        assert s.geoip_max_bytes == 12345
        assert s.geoip6_max_bytes == 67890

    def test_invalid_ipv6_limit_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_GEOIP6_MAX_BYTES"):
            Settings.from_mapping({"TORPROXY_GEOIP6_MAX_BYTES": "0"})

    def test_enabled_via_env(self):
        s = Settings.from_mapping({"TORPROXY_GEOIP_AUTO_UPDATE": "1"})
        assert s.geoip_auto_update is True

    def test_invalid_interval_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_GEOIP_UPDATE_INTERVAL"):
            Settings.from_mapping({"TORPROXY_GEOIP_UPDATE_INTERVAL": "0"})

    def test_non_https_url_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_GEOIP_URL"):
            Settings.from_mapping({"TORPROXY_GEOIP_URL": "http://example.com/geoip"})

    def test_relative_dir_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_GEOIP_DIR"):
            Settings.from_mapping({"TORPROXY_GEOIP_DIR": "relative/path"})


class TestGeoipValidation:
    def test_valid_ipv4_content(self):
        assert validate_geoip_content(GEOIP_V4, ipv6=False) is True

    def test_valid_ipv6_content(self):
        assert validate_geoip_content(GEOIP_V6, ipv6=True) is True

    def test_invalid_country_code_rejected(self):
        assert validate_geoip_content(b"16777216,16777471,DEU\n", ipv6=False) is False

    def test_unknown_country_code_accepted(self):
        # Upstream geoip/geoip6 mark ranges of unknown origin with
        # the literal code "??" (not a 2-letter ISO code).
        assert validate_geoip_content(b"394349824,394350079,??\n", ipv6=False) is True
        assert (
            validate_geoip_content(
                b"2000:b70:25::,2000:b70:25:ffff:ffff:ffff:ffff:ffff,??\n", ipv6=True
            )
            is True
        )

    def test_garbage_rejected(self):
        assert validate_geoip_content(b"<html>not found</html>\n", ipv6=False) is False

    def test_empty_rejected(self):
        assert validate_geoip_content(b"", ipv6=False) is False


class TestGeoipInstallAndFallback:
    def test_successful_install_writes_both_files(self, tmp_path):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        ok = update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
        assert ok is True
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4
        assert (tmp_path / "geoip6").read_bytes() == GEOIP_V6

    def test_network_failure_keeps_previous_good_files(self, tmp_path):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        assert (
            update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
            is True
        )
        # Second run: network fails -> previously installed files untouched.
        assert update_geoip(s, fetcher=_fetcher(error=OSError("offline"))) is False
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4
        assert (tmp_path / "geoip6").read_bytes() == GEOIP_V6

    def test_invalid_payload_keeps_previous_good_files(self, tmp_path):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        assert (
            update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
            is True
        )
        bad = _fetcher({s.geoip_url: b"garbage\n", s.geoip6_url: GEOIP_V6})
        assert update_geoip(s, fetcher=bad) is False
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4

    def test_per_file_limits_are_passed_to_the_fetcher(self, tmp_path):
        s = Settings.from_mapping(
            {
                "TORPROXY_GEOIP_AUTO_UPDATE": "1",
                "TORPROXY_GEOIP_DIR": str(tmp_path),
                "TORPROXY_GEOIP_MAX_BYTES": "111",
                "TORPROXY_GEOIP6_MAX_BYTES": "222",
            }
        )
        seen = {}

        def fetch(url: str, max_bytes: int) -> bytes:
            seen[url] = max_bytes
            return GEOIP_V4 if url == s.geoip_url else GEOIP_V6

        assert update_geoip(s, fetcher=fetch) is True
        assert seen == {s.geoip_url: 111, s.geoip6_url: 222}

    def test_successful_update_writes_status_file(self, tmp_path):
        import json

        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        assert (
            update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
            is True
        )
        status = json.loads((tmp_path / "geoip-status.json").read_text(encoding="utf-8"))
        assert status["source"] == "downloaded"
        assert status["last_error"] is None
        assert status["last_success_at"] is not None
        assert status["v4_bytes"] == len(GEOIP_V4)
        assert status["v6_bytes"] == len(GEOIP_V6)

    def test_failed_update_writes_status_file_with_last_error(self, tmp_path):
        import json

        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        assert update_geoip(s, fetcher=_fetcher(error=OSError("offline"))) is False
        status = json.loads((tmp_path / "geoip-status.json").read_text(encoding="utf-8"))
        assert status["source"] == "bundled"
        assert status["last_error"] == "offline"
        assert status["last_success_at"] is None
        assert status["last_attempt_at"] is not None

    def test_has_valid_geoip(self, tmp_path):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        assert has_valid_geoip(s) is False
        assert (
            update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
            is True
        )
        assert has_valid_geoip(s) is True


class TestGeoipTorrcRendering:
    TEMPLATE = (
        "SocksPort 0.0.0.0:__TORPROXY_SOCKS_PORT__\n"
        "ControlPort 127.0.0.1:9051\n"
        "GeoIPFile /usr/share/tor/geoip\n"
        "GeoIPv6File /usr/share/tor/geoip6\n"
    )

    def test_default_keeps_bundled_paths(self):
        s = Settings.from_mapping({})
        rendered = render_torrc(s, self.TEMPLATE)
        assert "GeoIPFile /usr/share/tor/geoip" in rendered
        assert "GeoIPv6File /usr/share/tor/geoip6" in rendered

    def test_active_fresh_db_points_to_geoip_dir(self):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": "/var/lib/tor/geoip"}
        )
        rendered = render_torrc(s, self.TEMPLATE, geoip_active=True)
        assert "GeoIPFile /var/lib/tor/geoip/geoip" in rendered
        assert "GeoIPv6File /var/lib/tor/geoip/geoip6" in rendered

    def test_fallback_keeps_bundled_paths(self):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": "/var/lib/tor/geoip"}
        )
        rendered = render_torrc(s, self.TEMPLATE, geoip_active=False)
        assert "GeoIPFile /usr/share/tor/geoip" in rendered
        assert "GeoIPv6File /usr/share/tor/geoip6" in rendered


class TestGeoipStatusObservability:
    """ISSUE-117: /status must surface the GeoIP outcome additively."""

    def _queries(self, geoip, tmp_path):
        from torproxy.queries import ProxyQueries
        from torproxy.service import ProxyService
        from torproxy.state import RuntimeState

        class FakeControl:
            def send(self, command):
                if command == "GETCONF DisableNetwork":
                    return "DisableNetwork=0", None
                return (
                    "250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 "
                    'TAG=done SUMMARY="Done"\r\n250 OK',
                    None,
                )

        class FakeEgress:
            def resolve(self):
                return "203.0.113.7", None

        class FakeSocks:
            def ready(self):
                return True

        class FakeClock:
            def monotonic(self):
                return 0.0

            def time(self):
                return 0.0

        settings = Settings.from_mapping({"TORPROXY_GEOIP_DIR": str(tmp_path)})
        service = ProxyService(
            settings,
            FakeControl(),
            FakeEgress(),
            FakeSocks(),
            RuntimeState(None, False, FakeClock()),
            geoip,
        )
        return ProxyQueries(service)

    def test_status_includes_geoip_snapshot(self, tmp_path):
        class StubGeoIp:
            def snapshot(self):
                return {
                    "source": "downloaded",
                    "last_attempt_at": 123.0,
                    "last_success_at": 123.0,
                    "last_error": None,
                    "v4_bytes": 10,
                    "v6_bytes": 20,
                }

        resp = self._queries(StubGeoIp(), tmp_path).status()
        assert resp.status == 200
        assert resp.body["status"] == "connected"
        assert resp.body["geoip"]["source"] == "downloaded"
        assert resp.body["geoip"]["last_error"] is None
        assert resp.body["geoip"]["v4_bytes"] == 10

    def test_status_geoip_unknown_without_adapter(self, tmp_path):
        resp = self._queries(None, tmp_path).status()
        assert resp.body["geoip"]["source"] == "unknown"
        assert resp.body["geoip"]["auto_update"] is False

    def test_file_adapter_reads_status_file(self, tmp_path):
        import json

        from torproxy.adapters.geoip_status import FileGeoIpStatus

        payload = {"source": "bundled", "last_error": "offline", "last_success_at": None}
        (tmp_path / "geoip-status.json").write_text(json.dumps(payload), encoding="utf-8")
        assert FileGeoIpStatus(str(tmp_path)).snapshot() == payload

    def test_file_adapter_missing_or_corrupt_returns_none(self, tmp_path):
        from torproxy.adapters.geoip_status import FileGeoIpStatus

        assert FileGeoIpStatus(str(tmp_path)).snapshot() is None
        (tmp_path / "geoip-status.json").write_text("not json", encoding="utf-8")
        assert FileGeoIpStatus(str(tmp_path)).snapshot() is None


class TestGeoipLoopAndMain:
    def test_run_loop_updates_and_sighups_once(self, tmp_path, monkeypatch):
        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        monkeypatch.setattr(
            "torproxy.runtime.geoip._https_fetch",
            _fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}),
        )
        sighups = []
        monkeypatch.setattr("torproxy.runtime.geoip._sighup_tor", lambda: sighups.append(True))
        calls = {"n": 0}

        def fake_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise KeyboardInterrupt

        monkeypatch.setattr("torproxy.runtime.geoip.time.sleep", fake_sleep)
        with pytest.raises(KeyboardInterrupt):
            run_loop(s)
        assert sighups == [True]
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4

    def test_sighup_tor_missing_pidfile_is_noop(self, monkeypatch):
        killed = []
        monkeypatch.setattr("torproxy.runtime.geoip.os.kill", lambda pid, sig: killed.append(pid))
        monkeypatch.setattr(
            "torproxy.runtime.geoip.Path.read_text",
            lambda self: (_ for _ in ()).throw(OSError()),
        )
        _sighup_tor()  # must not raise
        assert killed == []

    def test_main_disabled_is_noop(self, monkeypatch):
        monkeypatch.delenv("TORPROXY_GEOIP_AUTO_UPDATE", raising=False)
        monkeypatch.setattr(
            "torproxy.runtime.geoip.update_geoip", lambda s: (_ for _ in ()).throw(AssertionError())
        )
        main()  # default disabled -> no download attempt

    def test_main_once_downloads_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TORPROXY_GEOIP_AUTO_UPDATE", "1")
        monkeypatch.setenv("TORPROXY_GEOIP_DIR", str(tmp_path))
        monkeypatch.setattr(
            "torproxy.runtime.geoip._https_fetch",
            lambda url, max_bytes: GEOIP_V4 if url.endswith("/geoip") else GEOIP_V6,
        )
        monkeypatch.setattr("sys.argv", ["geoip", "--once"])
        main()
        assert (tmp_path / "geoip").exists()
