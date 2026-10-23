from unittest.mock import MagicMock, patch

import pytest

from torproxy import __version__
from torproxy.runtime.cli import build_parser, main


@pytest.mark.unit
class TestCli:
    def test_build_parser_has_version(self):
        parser = build_parser()
        assert parser.prog == "torproxy"

    def test_cli_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert f"torproxy {__version__}" in captured.out

    def test_cli_short_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["-v"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert f"torproxy {__version__}" in captured.out

    def test_cli_help_flag(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "usage: torproxy" in captured.out
        assert "Tor HTTP and SOCKS5 proxy" in captured.out

    def test_cli_starts_server_with_default_args(self, capsys):
        mock_server = MagicMock()
        mock_server.server_port = 8080

        with patch("torproxy.runtime.cli.create_server", return_value=mock_server) as mock_create:
            exit_code = main([])

        assert exit_code == 0
        mock_create.assert_called_once()
        mock_server.serve_forever.assert_called_once()
        mock_server.server_close.assert_called_once()
        captured = capsys.readouterr()
        assert "Starting API server on port 8080..." in captured.out
