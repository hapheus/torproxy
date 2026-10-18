import os
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKER_DIR = os.path.join(REPO_ROOT, "docker")


@pytest.mark.unit
class TestConfigTemplates:
    def test_privoxy_template_has_dynamic_socks_port(self):
        template_path = os.path.join(DOCKER_DIR, "privoxy.config.template")
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        msg = "privoxy.config.template must use __TORPROXY_SOCKS_PORT__ placeholder"
        assert "__TORPROXY_SOCKS_PORT__" in content, msg
        assert "forward-socks5t / 127.0.0.1:__TORPROXY_SOCKS_PORT__ ." in content
        assert "forward-socks5t / 127.0.0.1:9050 ." not in content

    def test_torrc_template_has_dynamic_socks_port(self):
        torrc_path = os.path.join(DOCKER_DIR, "torrc")
        with open(torrc_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "__TORPROXY_SOCKS_PORT__" in content
        assert "SocksPort 0.0.0.0:__TORPROXY_SOCKS_PORT__" in content

    def test_start_script_replaces_all_placeholders(self):
        start_script = os.path.join(DOCKER_DIR, "start.sh")
        with open(start_script, "r", encoding="utf-8") as f:
            content = f.read()

        assert '-e "s|__TORPROXY_SOCKS_PORT__|$TORPROXY_SOCKS_PORT|"' in content


@pytest.mark.unit
class TestShellScriptSyntax:
    @pytest.mark.parametrize("script", ["start.sh", "healthcheck.sh"])
    def test_bash_syntax_valid(self, script):
        script_path = os.path.join(DOCKER_DIR, script)
        res = subprocess.run(["bash", "-n", script_path], capture_output=True, text=True)
        assert res.returncode == 0, f"Bash syntax check failed for {script}: {res.stderr}"


@pytest.mark.unit
class TestStartScriptValidation:
    START_SCRIPT = os.path.join(DOCKER_DIR, "start.sh")

    def _run_validate(self, env_overrides):
        env = os.environ.copy()
        env.update(env_overrides)
        bash_cmd = (
            f"source <(sed -n '/^validate_configuration()/,/^}}/p' '{self.START_SCRIPT}'); "
            "validate_configuration"
        )
        return subprocess.run(["bash", "-c", bash_cmd], env=env, capture_output=True, text=True)

    def test_valid_default_configuration(self):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
        }
        res = self._run_validate(env)
        assert res.returncode == 0, f"Unexpected validation failure: {res.stderr}"

    @pytest.mark.parametrize("invalid_ip", [
        "999.999.999.999",
        "1.2.3",
        "1.2.3.4.5",
        "abc",
        "127.0.0.1a",
        "",
    ])
    def test_invalid_listen_address(self, invalid_ip):
        env = {
            "TORPROXY_LISTEN_ADDRESS": invalid_ip,
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
        }
        res = self._run_validate(env)
        assert res.returncode == 1
        assert "TORPROXY_LISTEN_ADDRESS" in res.stderr

    @pytest.mark.parametrize("port_var", [
        "TORPROXY_LISTEN_PORT",
        "TORPROXY_API_PORT",
        "TORPROXY_SOCKS_PORT",
    ])
    @pytest.mark.parametrize("invalid_port", ["0", "65536", "-1", "abc", ""])
    def test_invalid_ports(self, port_var, invalid_port):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
        }
        env[port_var] = invalid_port
        res = self._run_validate(env)
        assert res.returncode == 1
        assert port_var in res.stderr
        assert "between 1 and 65535" in res.stderr

    def test_conflicting_ports_rejected(self):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8080",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
        }
        res = self._run_validate(env)
        assert res.returncode == 1
        assert "Configuration error" in res.stderr
        assert "must all be distinct" in res.stderr
