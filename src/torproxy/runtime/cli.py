"""Environment access and process lifetime belong at the executable boundary."""

import os

from torproxy.bootstrap import create_server
from torproxy.configuration import Settings


def main() -> None:
    server = create_server(Settings.from_mapping(os.environ))
    try:
        print(f"Starting API server on port {server.server_port}...", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
