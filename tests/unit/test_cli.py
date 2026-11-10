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

    def test_cli_mcp_subcommand(self):
        mock_handler = MagicMock()
        with (
            patch(
                "torproxy.runtime.cli.create_mcp_handler", return_value=mock_handler
            ) as mock_create_handler,
            patch("torproxy.runtime.cli.run_stdio_server") as mock_run_stdio,
        ):
            exit_code = main(["mcp"])

        assert exit_code == 0
        mock_create_handler.assert_called_once()
        mock_run_stdio.assert_called_once_with(mock_handler)

    def test_cli_starts_mcp_sse_server_when_enabled(self, capsys):
        mock_server = MagicMock()
        mock_server.server_port = 8080
        mock_mcp = MagicMock()
        mock_mcp.server_address = ("0.0.0.0", 2501)

        with (
            patch("torproxy.runtime.cli.create_server", return_value=mock_server),
            patch(
                "torproxy.runtime.cli.create_mcp_server", return_value=mock_mcp
            ) as mock_create_mcp,
        ):
            exit_code = main([])

        assert exit_code == 0
        mock_create_mcp.assert_called_once()
        mock_mcp.server_close.assert_called_once()
        captured = capsys.readouterr()
        assert "Starting MCP SSE server on port 2501..." in captured.out

    def test_cli_does_not_start_mcp_when_disabled(self, monkeypatch, capsys):
        monkeypatch.setenv("TORPROXY_MCP_ENABLED", "false")
        mock_server = MagicMock()
        mock_server.server_port = 8080

        with (
            patch("torproxy.runtime.cli.create_server", return_value=mock_server),
            patch("torproxy.runtime.cli.create_mcp_server") as mock_create_mcp,
        ):
            exit_code = main([])

        assert exit_code == 0
        mock_create_mcp.assert_not_called()
        captured = capsys.readouterr()
        assert "Starting MCP SSE server" not in captured.out
