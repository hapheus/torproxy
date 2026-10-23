import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from torproxy.bootstrap import create_services
from torproxy.configuration import Settings
from torproxy.service import ControlFailure, InvalidInput


class FakeControl:
    def __init__(self):
        self.commands = []
        self.fail_on = None

    def send(self, command):
        self.commands.append(command)
        return (None, "failed") if command == self.fail_on else ("250 OK", None)


class FakeEgress:
    def resolve(self):
        return "198.51.100.10", None


def test_instances_do_not_share_state():
    first = create_services(Settings(), control=FakeControl(), egress=FakeEgress())
    second = create_services(Settings(), control=FakeControl(), egress=FakeEgress())
    first.mutate("reconnect", "DE", True)
    assert second.state.snapshot().country is None
    assert second.state.snapshot().reconnect_count == 0
    assert first.state.snapshot().reconnect_count == 1


def test_related_options_are_one_atomic_command():
    control = FakeControl()
    service = create_services(Settings(), control=control)
    service.mutate("connect", "DE,AT", True)
    assert control.commands == [
        'SETCONF ExitNodes="{de},{at}" StrictNodes=1',
        "SETCONF DisableNetwork=0",
    ]


def test_failed_configuration_preserves_state_and_blocks_action():
    control = FakeControl()
    control.fail_on = 'SETCONF ExitNodes="{de}" StrictNodes=1'
    service = create_services(Settings(), control=control)
    with pytest.raises(ControlFailure):
        service.mutate("reconnect", "DE", True)
    assert service.state.snapshot().country is None
    assert service.state.snapshot().strict_nodes is False
    assert service.state.snapshot().reconnect_count == 0
    assert len(control.commands) == 1


def test_successful_configuration_is_reported_after_later_action_failure():
    control = FakeControl()
    control.fail_on = "SIGNAL NEWNYM"
    service = create_services(Settings(), control=control)
    with pytest.raises(ControlFailure):
        service.mutate("reconnect", "DE", True)
    assert service.state.snapshot().country == "DE"
    assert service.state.snapshot().strict_nodes is True
    assert service.state.snapshot().reconnect_count == 0


def test_probe_in_flight_cannot_publish_after_disconnect():
    started, finish = threading.Event(), threading.Event()

    class SlowEgress:
        def resolve(self):
            started.set()
            assert finish.wait(3)
            return "198.51.100.20", None

    service = create_services(Settings(), control=FakeControl(), egress=SlowEgress())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.get_current_ip)
        try:
            assert started.wait(3)
            service.mutate("disconnect")
        finally:
            finish.set()
        ip, error = future.result(timeout=3)
    assert ip is None
    assert error
    assert service.state.cached_ip is None


def test_mutations_never_interleave():
    entered, release = threading.Event(), threading.Event()
    commands = []

    class BlockingControl:
        def send(self, command):
            commands.append(command)
            if command.startswith("SETCONF ExitNodes"):
                entered.set()
                assert release.wait(3)
            return "250 OK", None

    service = create_services(Settings(), control=BlockingControl())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.mutate, "connect", "AT")
        try:
            assert entered.wait(3)
            second = pool.submit(service.mutate, "disconnect")
            assert commands == ['SETCONF ExitNodes="{at}"']
        finally:
            release.set()
        first.result(timeout=3)
        second.result(timeout=3)
    assert commands == [
        'SETCONF ExitNodes="{at}"',
        "SETCONF DisableNetwork=0",
        "SETCONF DisableNetwork=1",
    ]


@pytest.mark.parametrize(
    "country,strict",
    [("DE\r\nSIGNAL HALT", None), ("DE", "invalid"), (["DE", 10], None), ("DE,,AT", None)],
)
def test_invalid_input_never_mutates(country, strict):
    control = FakeControl()
    service = create_services(Settings(), control=control)
    with pytest.raises(InvalidInput):
        service.mutate("reconnect", country, strict)
    assert not control.commands


def test_cache_uses_monotonic_time():
    class Clock:
        def __init__(self):
            self.elapsed = 0

        def monotonic(self):
            return self.elapsed

        def time(self):
            return 1000000 - self.elapsed * 100

    clock = Clock()
    service = create_services(Settings(), egress=FakeEgress(), clock=clock)
    assert service.get_current_ip() == ("198.51.100.10", None)
    clock.elapsed = 31
    assert service.state.snapshot().uptime == 31
    service.egress = type("Offline", (), {"resolve": lambda self: (None, "offline")})()
    assert service.get_current_ip() == (None, "offline")
