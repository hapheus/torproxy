"""Unit tests for optional periodic GeoIP auto-update (ISSUE-20).

Hermetic: no real network access. Downloads are faked via a stub fetcher.
"""

from __future__ import annotations

import pytest

from torproxy.configuration import Settings, render_torrc

GEOIP_V4 = b"# Last updated based on Test\n16777216,16777471,DE\n16777472,16777727,AT\n"
GEOIP_V6 = b"# Last updated based on Test\n2001:db8::,2001:db8:ffff:ffff:ffff:ffff:ffff:ffff,DE\n"


def _fetcher(pages: dict[str, bytes] | None = None, error: Exception | None = None):
    def fetch(url: str, max_bytes: int) -> bytes:
        if error is not None:
            raise error
        assert pages is not None
        return pages[url]

    return fetch


class TestGeoipSettings:
    def test_defaults_are_disabled_and_backward_compatible(self):
        s = Settings.from_mapping({})
        assert s.geoip_auto_update is False
        assert s.geoip_update_interval == 86400
        assert s.geoip_dir == "/var/lib/tor/geoip"
        assert s.geoip_url.startswith("https://gitlab.torproject.org/")
        assert s.geoip6_url.startswith("https://gitlab.torproject.org/")
        assert s.geoip_max_bytes == 10 * 1024 * 1024

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
        from torproxy.runtime.geoip import validate_geoip_content

        assert validate_geoip_content(GEOIP_V4, ipv6=False) is True

    def test_valid_ipv6_content(self):
        from torproxy.runtime.geoip import validate_geoip_content

        assert validate_geoip_content(GEOIP_V6, ipv6=True) is True

    def test_invalid_country_code_rejected(self):
        from torproxy.runtime.geoip import validate_geoip_content

        assert validate_geoip_content(b"16777216,16777471,DEU\n", ipv6=False) is False

    def test_garbage_rejected(self):
        from torproxy.runtime.geoip import validate_geoip_content

        assert validate_geoip_content(b"<html>not found</html>\n", ipv6=False) is False

    def test_empty_rejected(self):
        from torproxy.runtime.geoip import validate_geoip_content

        assert validate_geoip_content(b"", ipv6=False) is False


class TestGeoipInstallAndFallback:
    def test_successful_install_writes_both_files(self, tmp_path):
        from torproxy.runtime.geoip import update_geoip

        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        ok = update_geoip(s, fetcher=_fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}))
        assert ok is True
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4
        assert (tmp_path / "geoip6").read_bytes() == GEOIP_V6

    def test_network_failure_keeps_previous_good_files(self, tmp_path):
        from torproxy.runtime.geoip import update_geoip

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
        from torproxy.runtime.geoip import update_geoip

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

    def test_has_valid_geoip(self, tmp_path):
        from torproxy.runtime.geoip import has_valid_geoip, update_geoip

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


class TestGeoipLoopAndMain:
    def test_run_loop_updates_and_sighups_once(self, tmp_path, monkeypatch):
        import torproxy.runtime.geoip as geoip

        s = Settings.from_mapping(
            {"TORPROXY_GEOIP_AUTO_UPDATE": "1", "TORPROXY_GEOIP_DIR": str(tmp_path)}
        )
        monkeypatch.setattr(
            geoip,
            "_https_fetch",
            _fetcher({s.geoip_url: GEOIP_V4, s.geoip6_url: GEOIP_V6}),
        )
        sighups = []
        monkeypatch.setattr(geoip, "_sighup_tor", lambda: sighups.append(True))
        calls = {"n": 0}

        def fake_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise KeyboardInterrupt

        monkeypatch.setattr(geoip.time, "sleep", fake_sleep)
        with pytest.raises(KeyboardInterrupt):
            geoip.run_loop(s)
        assert sighups == [True]
        assert (tmp_path / "geoip").read_bytes() == GEOIP_V4

    def test_sighup_tor_missing_pidfile_is_noop(self, monkeypatch):
        import torproxy.runtime.geoip as geoip

        killed = []
        monkeypatch.setattr(geoip.os, "kill", lambda pid, sig: killed.append(pid))
        monkeypatch.setattr(geoip.Path, "read_text", lambda self: (_ for _ in ()).throw(OSError()))
        geoip._sighup_tor()  # must not raise
        assert killed == []

    def test_main_disabled_is_noop(self, monkeypatch):
        import torproxy.runtime.geoip as geoip

        monkeypatch.delenv("TORPROXY_GEOIP_AUTO_UPDATE", raising=False)
        monkeypatch.setattr(
            geoip, "update_geoip", lambda s: (_ for _ in ()).throw(AssertionError())
        )
        geoip.main()  # default disabled -> no download attempt

    def test_main_once_downloads_when_enabled(self, tmp_path, monkeypatch):
        import torproxy.runtime.geoip as geoip

        monkeypatch.setenv("TORPROXY_GEOIP_AUTO_UPDATE", "1")
        monkeypatch.setenv("TORPROXY_GEOIP_DIR", str(tmp_path))
        monkeypatch.setattr(
            geoip,
            "_https_fetch",
            lambda url, max_bytes: GEOIP_V4 if url.endswith("/geoip") else GEOIP_V6,
        )
        monkeypatch.setattr("sys.argv", ["geoip", "--once"])
        geoip.main()
        assert (tmp_path / "geoip").exists()
