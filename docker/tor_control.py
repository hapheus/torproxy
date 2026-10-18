#!/usr/bin/env python3
import os
import socket

DEFAULT_CONTROL_PORT = int(os.environ.get("TOR_CONTROL_PORT", "9051"))
DEFAULT_COOKIE_PATH = os.environ.get("TOR_CONTROL_COOKIE_FILE", "/var/lib/tor/control_auth_cookie")


class TorControlError(Exception):
    """Raised when an unrecoverable protocol or socket error occurs."""


def _read_raw_line(sock, buffer):
    """Reads characters from buffer or socket until CRLF or LF is encountered."""
    while True:
        if b"\r\n" in buffer:
            line_bytes, buffer = buffer.split(b"\r\n", 1)
            return line_bytes.decode("utf-8", errors="replace"), buffer
        if b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            return line_bytes.decode("utf-8", errors="replace"), buffer

        chunk = sock.recv(1024)
        if not chunk:
            raise TorControlError("Unexpected EOF while reading from Tor control socket")
        buffer += chunk


def read_reply(sock):
    """Reads a complete Tor Control Protocol reply according to TC-spec.

    Returns:
        (int, list[str]): A tuple of (final_status_code, list_of_lines).
    """
    buffer = b""
    lines = []
    final_code = None

    while True:
        line, buffer = _read_raw_line(sock, buffer)
        lines.append(line)

        # A Tor control line starts with a 3-digit status code
        if len(line) < 3 or not line[:3].isdigit():
            raise TorControlError(f"Malformed line from Tor control: {line!r}")

        code = int(line[:3])
        separator = line[3:4]

        if separator == " " or len(line) == 3:
            # Final line of a single or multiline reply
            final_code = code
            break
        elif separator == "-":
            # Multiline continuation
            continue
        elif separator == "+":
            # Multiline data block ending with a single '.' on its own line
            while True:
                data_line, buffer = _read_raw_line(sock, buffer)
                if data_line == ".":
                    break
                lines.append(data_line)
        else:
            raise TorControlError(f"Unrecognized separator in Tor control reply: {line!r}")

    return final_code, lines


def authenticate(sock, cookie_path=None):
    """Authenticates with the Tor control port using a cookie or blank credentials."""
    target_cookie = cookie_path or DEFAULT_COOKIE_PATH

    cookie_hex = None
    if target_cookie and os.path.exists(target_cookie):
        try:
            with open(target_cookie, "rb") as f:
                cookie_data = f.read()
                cookie_hex = cookie_data.hex()
        except OSError:
            cookie_hex = None

    if cookie_hex:
        # Authenticate using hex-encoded cookie
        cmd = f"AUTHENTICATE {cookie_hex}\r\n".encode("ascii")
    else:
        # Fallback to empty authentication for CookieAuthentication 0
        cmd = b"AUTHENTICATE\r\n"

    try:
        sock.sendall(cmd)
        code, lines = read_reply(sock)
        if code != 250:
            error_msg = lines[-1] if lines else str(code)
            return False, f"Tor control authentication failed: {error_msg}"
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"Tor control authentication socket error: {e}"


def send_command(
    command, host="127.0.0.1", port=DEFAULT_CONTROL_PORT, timeout=3.0, cookie_path=None
):
    """Sends a single command to Tor ControlPort and returns (response_string, error_string)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))

            auth_ok, auth_err = authenticate(s, cookie_path=cookie_path)
            if not auth_ok:
                return None, auth_err

            formatted_cmd = command.strip() + "\r\n"
            s.sendall(formatted_cmd.encode("utf-8"))

            code, lines = read_reply(s)
            if code != 250:
                detail = lines[-1] if lines else f"status {code}"
                return None, f"Tor control error: {detail}"

            reply_text = "\r\n".join(lines) + "\r\n"
            return reply_text, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)
