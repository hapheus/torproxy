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
