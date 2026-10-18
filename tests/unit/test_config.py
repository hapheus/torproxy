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
        assert res.returncode == 0, (
            f"Valid country '{valid_country}' unexpectedly failed: {res.stderr}"
        )

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
        rendered_torrc = str(tmp_path / "torrc")

        # Execute the torrc generation block with /tmp/torrc redirected to tmp_path
        script = f"""
            sed -e "s|__TORPROXY_SOCKS_PORT__|$TORPROXY_SOCKS_PORT|" \\
                "{torrc_template}" > "{rendered_torrc}"
            exit_nodes=""
            country_input="${{TORPROXY_COUNTRY:-${{TORPROXY_EXIT_COUNTRY:-}}}}"
            if [[ -n "$country_input" ]]; then
              cleaned="${{country_input// /}}"
              IFS=',' read -r -a ccs <<< "$cleaned"
              formatted=""
              for c in "${{ccs[@]}}"; do
                lower_c=$(echo "$c" | tr '[:upper:]' '[:lower:]')
                if [[ -z "$formatted" ]]; then
                  formatted="{{$lower_c}}"
                else
                  formatted="${{formatted}},{{$lower_c}}"
                fi
              done
              exit_nodes="$formatted"
            elif [[ -n "${{TORPROXY_EXIT_NODES:-}}" ]]; then
              exit_nodes="${{TORPROXY_EXIT_NODES}}"
            fi

            if [[ -n "$exit_nodes" ]]; then
              echo "ExitNodes $exit_nodes" >> "{rendered_torrc}"
              strict_val="${{TORPROXY_STRICT_NODES:-1}}"
              if [[ "$strict_val" =~ ^(1|true|yes|TRUE|YES)$ ]]; then
                echo "StrictNodes 1" >> "{rendered_torrc}"
              else
                echo "StrictNodes 0" >> "{rendered_torrc}"
              fi
            elif [[ -n "${{TORPROXY_STRICT_NODES:-}}" ]]; then
              strict_val="${{TORPROXY_STRICT_NODES}}"
              if [[ "$strict_val" =~ ^(1|true|yes|TRUE|YES)$ ]]; then
                echo "StrictNodes 1" >> "{rendered_torrc}"
              else
                echo "StrictNodes 0" >> "{rendered_torrc}"
              fi
            fi
        """
        res = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        assert res.returncode == 0, f"Script failed: {res.stderr}"
        with open(rendered_torrc, "r", encoding="utf-8") as f:
            return f.read()

    def test_default_renders_no_exit_nodes(self, tmp_path):
        content = self._render_torrc({}, tmp_path)
        assert "ExitNodes" not in content
        assert "StrictNodes" not in content

    def test_single_country_code(self, tmp_path):
        content = self._render_torrc({"TORPROXY_COUNTRY": "DE"}, tmp_path)
        assert "ExitNodes {de}" in content
        assert "StrictNodes 1" in content

    def test_multi_country_code_case_insensitive(self, tmp_path):
        content = self._render_torrc({"TORPROXY_COUNTRY": "de, AT, us"}, tmp_path)
        assert "ExitNodes {de},{at},{us}" in content
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
        assert "StrictNodes 1" in content


