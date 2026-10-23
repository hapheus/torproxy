"""Validate settings or render daemon configuration before starting processes."""

import os
import sys
from pathlib import Path

from torproxy.configuration import Settings, render_torrc


def main() -> None:
    try:
        settings = Settings.from_mapping(os.environ)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    if sys.argv[1:] == ["--check"]:
        return
    template = Path("/etc/privoxy/config.template").read_text()
    for key, value in (
        ("LISTEN_ADDRESS", settings.listen_address),
        ("LISTEN_PORT", str(settings.proxy_port)),
        ("SOCKS_PORT", str(settings.socks_port)),
    ):
        template = template.replace(f"__TORPROXY_{key}__", value)
    Path("/tmp/privoxy.config").write_text(template)
    Path("/tmp/torrc").write_text(render_torrc(settings, Path("/etc/tor/torrc").read_text()))


if __name__ == "__main__":
    main()
