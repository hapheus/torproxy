import socket
from unittest.mock import MagicMock, patch

import pytest
import tor_control


@pytest.mark.unit
class TestTorControlReplyParser:
    def test_parse_single_line_success(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250 OK\r\n"]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 250
        assert lines == ["250 OK"]

    def test_parse_multiline_hyphen(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            (
                b"250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done "
                b'SUMMARY="Handshake"\r\n'
                b"250 OK\r\n"
            )
        ]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 250
        assert len(lines) == 2
        assert "PROGRESS=100" in lines[0]
        assert lines[1] == "250 OK"

    def test_parse_multiline_data_block(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"250+config-text=\r\nDataDirectory /var/lib/tor\r\n.\r\n250 OK\r\n"
        ]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 250
        assert "DataDirectory /var/lib/tor" in lines
        assert lines[-1] == "250 OK"

    def test_parse_fragmented_tcp_chunks(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"25",
            b"0-status=foo\r",
            b"\n250 ",
            b"OK\r\n",
        ]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 250
        assert lines == ["250-status=foo", "250 OK"]

    def test_parse_error_status_code_552(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"552 Unrecognized configuration key\r\n"]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 552
        assert lines == ["552 Unrecognized configuration key"]

    def test_parse_unexpected_eof(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250-partial", b""]
        with pytest.raises(tor_control.TorControlError, match="EOF"):
            tor_control.read_reply(mock_sock)

    def test_parse_unix_newline_lf(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250 OK\n"]
        code, lines = tor_control.read_reply(mock_sock)
        assert code == 250
        assert lines == ["250 OK"]

    def test_parse_malformed_short_line(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"OK\r\n"]
        with pytest.raises(tor_control.TorControlError, match="Malformed line"):
            tor_control.read_reply(mock_sock)

    def test_parse_malformed_non_digit_code(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"ABC OK\r\n"]
        with pytest.raises(tor_control.TorControlError, match="Malformed line"):
            tor_control.read_reply(mock_sock)

    def test_parse_unrecognized_separator(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250*Unrecognized\r\n"]
        with pytest.raises(tor_control.TorControlError, match="Unrecognized separator"):
            tor_control.read_reply(mock_sock)


@pytest.mark.unit
class TestTorControlAuthentication:
    def test_authenticate_with_cookie_file(self, tmp_path):
        cookie_bytes = b"\x01" * 32
        cookie_file = tmp_path / "control_auth_cookie"
        cookie_file.write_bytes(cookie_bytes)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250 OK\r\n"]

        success, err = tor_control.authenticate(mock_sock, cookie_path=str(cookie_file))

        assert success is True
        assert err is None
        expected_hex = cookie_bytes.hex()
        expected_cmd = f"AUTHENTICATE {expected_hex}\r\n".encode("ascii")
        mock_sock.sendall.assert_called_once_with(expected_cmd)

    def test_authenticate_missing_cookie_fallback(self):
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250 OK\r\n"]

        success, err = tor_control.authenticate(mock_sock, cookie_path="/nonexistent/cookie")

        assert success is True
        assert err is None
        mock_sock.sendall.assert_called_once_with(b"AUTHENTICATE\r\n")

    def test_authenticate_cookie_read_oserror(self, tmp_path):
        cookie_file = tmp_path / "unreadable_cookie"
        cookie_file.write_bytes(b"\x00" * 32)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"250 OK\r\n"]

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            success, err = tor_control.authenticate(mock_sock, cookie_path=str(cookie_file))
            assert success is True
            assert err is None
            # Fallback to empty AUTHENTICATE
            mock_sock.sendall.assert_called_once_with(b"AUTHENTICATE\r\n")

    def test_authenticate_failure_redacts_credentials(self, tmp_path):
        cookie_bytes = b"\x02" * 32
        cookie_file = tmp_path / "control_auth_cookie"
        cookie_file.write_bytes(cookie_bytes)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"515 Authentication failed\r\n"]

        success, err = tor_control.authenticate(mock_sock, cookie_path=str(cookie_file))

        assert success is False
        assert "515" in err
        # Ensure cookie hex is never logged or contained in the error message
        assert cookie_bytes.hex() not in err

    def test_authenticate_socket_exception(self):
        mock_sock = MagicMock()
        mock_sock.sendall.side_effect = socket.error("Connection reset by peer")

        success, err = tor_control.authenticate(mock_sock, cookie_path="/nonexistent")
        assert success is False
        assert "socket error" in err


@pytest.mark.unit
class TestTorControlCommandExecution:
    @patch("tor_control.socket.socket")
    def test_execute_command_success(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b"250 OK\r\n",  # Auth reply
            b"250 OK\r\n",  # Command reply
        ]

        resp, err = tor_control.send_command("SIGNAL NEWNYM", cookie_path="/nonexistent")

        assert err is None
        assert resp == "250 OK\r\n"
        mock_sock.sendall.assert_any_call(b"SIGNAL NEWNYM\r\n")

    @patch("tor_control.socket.socket")
    def test_execute_command_rejected_by_tor(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b"250 OK\r\n",  # Auth reply
            b"552 Unknown configuration option 'InvalidOption'\r\n",
        ]

        resp, err = tor_control.send_command("SETCONF InvalidOption=1", cookie_path="/nonexistent")

        assert resp is None
        assert "Unknown configuration option" in err

    @patch("tor_control.socket.socket")
    def test_execute_command_socket_timeout(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.connect.side_effect = socket.timeout("timed out")

        resp, err = tor_control.send_command("GETINFO version", cookie_path="/nonexistent")

        assert resp is None
        assert "timed out" in err

    @patch("tor_control.socket.socket")
    def test_execute_command_auth_failure(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b"515 Bad authentication\r\n",  # Auth reply fails
        ]

        resp, err = tor_control.send_command("SIGNAL NEWNYM", cookie_path="/nonexistent")
        assert resp is None
        assert "Tor control authentication failed" in err
