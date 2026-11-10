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

        assert "python3 -m torproxy.runtime.configure" in content


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

    @pytest.mark.parametrize(
        "invalid_ip",
        [
            "999.999.999.999",
            "1.2.3",
            "1.2.3.4.5",
            "abc",
            "127.0.0.1a",
            "",
        ],
    )
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

    @pytest.mark.parametrize(
        "port_var",
        [
            "TORPROXY_LISTEN_PORT",
            "TORPROXY_API_PORT",
            "TORPROXY_SOCKS_PORT",
        ],
    )
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

    @pytest.mark.parametrize("valid_country", ["DE", "at", "de,at", "US, GB, FR", "ch", "NL,SE,no"])
    def test_valid_country_codes(self, valid_country):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
            "TORPROXY_COUNTRY": valid_country,
        }
        res = self._run_validate(env)
        err_msg = f"Valid country '{valid_country}' unexpectedly failed: {res.stderr}"
        assert res.returncode == 0, err_msg

    @pytest.mark.parametrize(
        "invalid_country", ["GER", "12", "D", "DE,,AT", "DE;AT", "!#", "DE 12"]
    )
    def test_invalid_country_codes(self, invalid_country):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
            "TORPROXY_COUNTRY": invalid_country,
        }
        res = self._run_validate(env)
        assert res.returncode == 1
        assert "TORPROXY_COUNTRY" in res.stderr

    @pytest.mark.parametrize(
        "valid_strict", ["0", "1", "true", "false", "yes", "no", "TRUE", "False"]
    )
    def test_valid_strict_nodes(self, valid_strict):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
            "TORPROXY_COUNTRY": "DE",
            "TORPROXY_STRICT_NODES": valid_strict,
        }
        res = self._run_validate(env)
        assert res.returncode == 0, f"Valid strict_nodes '{valid_strict}' failed: {res.stderr}"

    @pytest.mark.parametrize("invalid_strict", ["2", "-1", "maybe", "strict", "none"])
    def test_invalid_strict_nodes(self, invalid_strict):
        env = {
            "TORPROXY_LISTEN_ADDRESS": "0.0.0.0",
            "TORPROXY_LISTEN_PORT": "8118",
            "TORPROXY_API_PORT": "8080",
            "TORPROXY_SOCKS_PORT": "9050",
            "TORPROXY_STRICT_NODES": invalid_strict,
        }
        res = self._run_validate(env)
        assert res.returncode == 1
        assert "TORPROXY_STRICT_NODES" in res.stderr


@pytest.mark.unit
class TestTorrcGeneration:
    START_SCRIPT = os.path.join(DOCKER_DIR, "start.sh")

    def _render_torrc(self, env_overrides, tmp_path):
        env = os.environ.copy()
        env.update(env_overrides)
        env["TORPROXY_SOCKS_PORT"] = "9050"
        torrc_template = os.path.join(DOCKER_DIR, "torrc")

        # Execute the torrc generation block
        from pathlib import Path

        from torproxy.configuration import Settings, render_torrc

        return render_torrc(Settings.from_mapping(env), Path(torrc_template).read_text())

    def test_default_renders_no_exit_nodes(self, tmp_path):
        content = self._render_torrc({}, tmp_path)
        assert "ExitNodes" not in content
        assert "StrictNodes" not in content

    def test_single_country_code(self, tmp_path):
        content = self._render_torrc({"TORPROXY_COUNTRY": "DE"}, tmp_path)
        assert "ExitNodes {de}" in content
        assert "StrictNodes 0" in content

    def test_multi_country_code_case_insensitive(self, tmp_path):
        content = self._render_torrc({"TORPROXY_COUNTRY": "de, AT, us"}, tmp_path)
        assert "ExitNodes {de},{at},{us}" in content
        assert "StrictNodes 0" in content

    def test_country_without_strict_defaults_to_not_strict(self, tmp_path):
        # ISSUE-04: TORPROXY_COUNTRY alone must not implicitly enable strict mode.
        content = self._render_torrc({"TORPROXY_COUNTRY": "DE"}, tmp_path)
        assert "StrictNodes 0" in content

    def test_exit_nodes_without_strict_defaults_to_not_strict(self, tmp_path):
        content = self._render_torrc({"TORPROXY_EXIT_NODES": "{ch},{nl}"}, tmp_path)
        assert "StrictNodes 0" in content

    def test_country_with_explicit_strict_enabled(self, tmp_path):
        content = self._render_torrc(
            {"TORPROXY_COUNTRY": "DE", "TORPROXY_STRICT_NODES": "1"}, tmp_path
        )
        assert "ExitNodes {de}" in content
        assert "StrictNodes 1" in content

    def test_country_with_strict_nodes_disabled(self, tmp_path):
        content = self._render_torrc(
            {"TORPROXY_COUNTRY": "AT", "TORPROXY_STRICT_NODES": "0"}, tmp_path
        )
        assert "ExitNodes {at}" in content
        assert "StrictNodes 0" in content

    def test_direct_exit_nodes_override(self, tmp_path):
        content = self._render_torrc({"TORPROXY_EXIT_NODES": "{ch},{nl}"}, tmp_path)
        assert "ExitNodes {ch},{nl}" in content
        assert "StrictNodes 0" in content


@pytest.mark.unit
class TestApiTokenSettings:
    def test_default_api_token_is_none(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({})
        assert s.api_token is None
        assert s.api_allow_anonymous_health is False
        assert s.api_listen_address == "0.0.0.0"

    def test_api_token_from_env(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_API_TOKEN": "secret123"})
        assert s.api_token == "secret123"

    def test_api_key_fallback(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_API_KEY": "secret_key_abc"})
        assert s.api_token == "secret_key_abc"

    def test_empty_or_whitespace_token_treated_as_none(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_API_TOKEN": "   "})
        assert s.api_token is None

    def test_allow_anonymous_health_parsing(self):
        from torproxy.configuration import Settings

        s1 = Settings.from_mapping({"TORPROXY_API_ALLOW_ANONYMOUS_HEALTH": "1"})
        assert s1.api_allow_anonymous_health is True

        s2 = Settings.from_mapping({"TORPROXY_API_ALLOW_ANONYMOUS_HEALTH": "true"})
        assert s2.api_allow_anonymous_health is True

        s3 = Settings.from_mapping({"TORPROXY_API_ALLOW_ANONYMOUS_HEALTH": "0"})
        assert s3.api_allow_anonymous_health is False

    def test_api_listen_address_parsing(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_API_LISTEN_ADDRESS": "127.0.0.1"})
        assert s.api_listen_address == "127.0.0.1"


@pytest.mark.unit
class TestGatewaySettings:
    def test_default_gateway_settings(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({})
        assert s.gateway_mode is False
        assert s.trans_port == 9040
        assert s.dns_port == 9053

    @pytest.mark.parametrize("val", ["1", "true", "yes", "TRUE", "True"])
    def test_gateway_mode_enabled_truthy(self, val):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_GATEWAY_MODE": val})
        assert s.gateway_mode is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "FALSE", "False", ""])
    def test_gateway_mode_disabled_falsy(self, val):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({"TORPROXY_GATEWAY_MODE": val})
        assert s.gateway_mode is False

    def test_custom_gateway_ports(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping(
            {
                "TORPROXY_GATEWAY_MODE": "1",
                "TORPROXY_TRANS_PORT": "9041",
                "TORPROXY_DNS_PORT": "9054",
            }
        )
        assert s.trans_port == 9041
        assert s.dns_port == 9054

    @pytest.mark.parametrize("invalid_port", ["0", "65536", "-5", "abc"])
    def test_invalid_gateway_ports(self, invalid_port):
        from torproxy.configuration import Settings

        with pytest.raises(
            ValueError, match="must be an integer between 1 and 65535|must be between 1 and 65535"
        ):
            Settings.from_mapping(
                {
                    "TORPROXY_GATEWAY_MODE": "1",
                    "TORPROXY_TRANS_PORT": invalid_port,
                }
            )

    def test_gateway_port_collision_with_socks(self):
        from torproxy.configuration import Settings

        with pytest.raises(ValueError, match="distinct ports"):
            Settings.from_mapping(
                {
                    "TORPROXY_GATEWAY_MODE": "1",
                    "TORPROXY_TRANS_PORT": "9050",  # collides with socks_port default 9050
                }
            )

    def test_render_torrc_with_gateway_mode(self):
        from torproxy.configuration import Settings, render_torrc

        template = "SocksPort 0.0.0.0:__TORPROXY_SOCKS_PORT__\nControlPort 127.0.0.1:9051\n"
        settings = Settings.from_mapping(
            {
                "TORPROXY_GATEWAY_MODE": "1",
                "TORPROXY_TRANS_PORT": "9040",
                "TORPROXY_DNS_PORT": "9053",
            }
        )
        rendered = render_torrc(settings, template)
        assert "TransPort 127.0.0.1:9040" in rendered
        assert "DNSPort 127.0.0.1:9053" in rendered

    def test_render_torrc_without_gateway_mode(self):
        from torproxy.configuration import Settings, render_torrc

        template = "SocksPort 0.0.0.0:__TORPROXY_SOCKS_PORT__\nControlPort 127.0.0.1:9051\n"
        settings = Settings.from_mapping({"TORPROXY_GATEWAY_MODE": "0"})
        rendered = render_torrc(settings, template)
        assert "TransPort" not in rendered
        assert "DNSPort" not in rendered


@pytest.mark.unit
class TestMcpSettings:
    def test_default_mcp_settings(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping({})
        assert s.mcp_enabled is True
        assert s.mcp_port == 2501
        assert s.mcp_listen_address == "0.0.0.0"

    def test_custom_mcp_settings(self):
        from torproxy.configuration import Settings

        s = Settings.from_mapping(
            {
                "TORPROXY_MCP_ENABLED": "false",
                "TORPROXY_MCP_PORT": "2502",
                "TORPROXY_MCP_LISTEN_ADDRESS": "127.0.0.1",
            }
        )
        assert s.mcp_enabled is False
        assert s.mcp_port == 2502
        assert s.mcp_listen_address == "127.0.0.1"

    @pytest.mark.parametrize("invalid_port", ["0", "65536", "-1", "xyz"])
    def test_invalid_mcp_port(self, invalid_port):
        from torproxy.configuration import Settings

        with pytest.raises(ValueError):
            Settings.from_mapping({"TORPROXY_MCP_PORT": invalid_port})

    def test_invalid_mcp_listen_address(self):
        from torproxy.configuration import Settings

        with pytest.raises(ValueError, match="TORPROXY_MCP_LISTEN_ADDRESS"):
            Settings.from_mapping({"TORPROXY_MCP_LISTEN_ADDRESS": "not-an-ip"})

    def test_mcp_port_collision_with_api_port(self):
        from torproxy.configuration import Settings

        with pytest.raises(ValueError, match="distinct ports"):
            Settings.from_mapping({"TORPROXY_MCP_PORT": "8080"})

    def test_dockerfile_installs_torproxy_cli_binary(self):
        from pathlib import Path

        dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")
        assert "/usr/local/bin/torproxy" in dockerfile
        assert "torproxy --version" in dockerfile
