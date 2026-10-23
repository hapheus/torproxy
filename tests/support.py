"""Shared instance for the original HTTP characterization tests."""

from torproxy.bootstrap import create_services
from torproxy.configuration import Settings

api = create_services(Settings())
