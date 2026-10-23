#!/usr/bin/env python3
import socket

DEFAULT_CONTROL_PORT = 9051
DEFAULT_COOKIE_PATH = "/var/lib/tor/control_auth_cookie"


class TorControlError(Exception):
    """Raised when an unrecoverable protocol or socket error occurs."""


def _read_raw_line(sock: socket.socket, buffer: bytes) -> tuple[str, bytes]:
    """Reads characters from buffer or socket until CRLF or LF is encountered."""
    while True:
        if b"\r\n" in buffer:
            line_bytes, buffer = buffer.split(b"\r\n", 1)
            return line_bytes.decode("utf-8", errors="replace"), buffer
        if b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            return line_bytes.decode("utf-8", errors="replace"), buffer

        if len(buffer) > 65536:
            raise TorControlError("Tor control line exceeds size limit")
        chunk = sock.recv(1024)
        if not chunk:
            raise TorControlError("Unexpected EOF while reading from Tor control socket")
        buffer += chunk


def read_reply(sock: socket.socket) -> tuple[int, list[str]]:
    """Reads a complete Tor Control Protocol reply according to TC-spec.

    Returns:
        (int, list[str]): A tuple of (final_status_code, list_of_lines).
    """
    buffer = b""
    lines = []
    final_code = None
    total_bytes = 0

    while True:
        line, buffer = _read_raw_line(sock, buffer)
        total_bytes += len(line) + 2
        if total_bytes > 262144:
            raise TorControlError("Tor control reply exceeds size limit")
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
                total_bytes += len(data_line) + 2
                if total_bytes > 262144:
                    raise TorControlError("Tor control reply exceeds size limit")
                lines.append(data_line)
        else:
            raise TorControlError(f"Unrecognized separator in Tor control reply: {line!r}")

    return final_code, lines


def authenticate(sock: socket.socket, cookie_path: str | None = None) -> tuple[bool, str | None]:
    """Authenticates with the Tor control port using a mandatory 32-byte cookie."""
    target_cookie = cookie_path or DEFAULT_COOKIE_PATH

    try:
        with open(target_cookie, "rb") as cookie:
            cookie_data = cookie.read(33)
        if len(cookie_data) != 32:
            return False, "Tor control authentication requires a 32-byte cookie"
    except OSError:
        return False, "Tor control authentication cookie unavailable"
    cookie_hex = cookie_data.hex()
    cmd = f"AUTHENTICATE {cookie_hex}\r\n".encode("ascii")

    try:
        sock.sendall(cmd)
        code, lines = read_reply(sock)
        if code != 250:
            error_msg = str(code)
            return False, f"Tor control authentication failed: {error_msg}"
        return True, None
    except (OSError, TorControlError):
        return False, "Tor control authentication socket error"


def send_command(
    command: str,
    host: str = "127.0.0.1",
    port: int = DEFAULT_CONTROL_PORT,
    timeout: float = 3.0,
    cookie_path: str | None = None,
) -> tuple[str | None, str | None]:
    """Sends a single command to Tor ControlPort and returns (response_string, error_string)."""
    if not command.strip() or "\r" in command or "\n" in command or len(command) > 4096:
        return None, "Invalid Tor control command"
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


class TorControlClient:
    """Authenticated one-command connections; configuration is explicit."""

    def __init__(self, port: int, cookie_path: str, timeout: float = 3) -> None:
        self.port = port
        self.cookie_path = cookie_path
        self.timeout = timeout

    def send(self, command: str) -> tuple[str | None, str | None]:
        return send_command(
            command, port=self.port, cookie_path=self.cookie_path, timeout=self.timeout
        )
