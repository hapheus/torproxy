import os

import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")

EXAMPLE_SPECS = {
    "browserless-chromium-via-tor": {
        "consumer": "browserless",
        "proxy_config_type": "env",
        "proxy_target": "http://torproxy:8118",
    },
    "crw-web-scraper-via-tor": {
        "consumer": "crw",
        "proxy_config_type": "env",
        "proxy_target": "http://torproxy:8118",
    },
    "searxng-via-tor": {
        "consumer": "searxng",
        "proxy_config_type": "settings",
        "proxy_target": "http://torproxy:8118",
    },
}


@pytest.mark.unit
class TestExamplesIntegrity:
    """Automated verification of shipped examples, compose files, and security contracts."""

    @pytest.mark.parametrize("example_name", list(EXAMPLE_SPECS.keys()))
    def test_compose_yaml_validity(self, example_name):
        compose_path = os.path.join(EXAMPLES_DIR, example_name, "docker-compose.yml")
        assert os.path.exists(compose_path), f"Missing docker-compose.yml in {example_name}"

        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "services" in data, f"{example_name} docker-compose.yml missing 'services' key"
        services = data["services"]
        assert "torproxy" in services, f"{example_name} missing 'torproxy' service"
        consumer_name = EXAMPLE_SPECS[example_name]["consumer"]
        assert consumer_name in services, f"{example_name} missing '{consumer_name}' service"

    @pytest.mark.parametrize("example_name", list(EXAMPLE_SPECS.keys()))
    def test_torproxy_service_contracts(self, example_name):
        compose_path = os.path.join(EXAMPLES_DIR, example_name, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        tor_service = data["services"]["torproxy"]
        assert tor_service["image"] == "hapheus/torproxy:latest"
        assert tor_service.get("restart") == "unless-stopped"

        # torproxy in examples must communicate internally via Docker network
        # and MUST NOT publish ports to host
        no_ports = "ports" not in tor_service or not tor_service["ports"]
        assert no_ports, f"torproxy service in {example_name} unexpectedly publishes ports to host"

        env = tor_service.get("environment", {})
        if isinstance(env, dict):
            assert env.get("TORPROXY_LISTEN_PORT") == 8118
            assert env.get("TORPROXY_API_PORT") == 8080
            assert env.get("TORPROXY_SOCKS_PORT") == 9050

    @pytest.mark.parametrize("example_name", list(EXAMPLE_SPECS.keys()))
    def test_consumer_service_dependency_and_ports(self, example_name):
        compose_path = os.path.join(EXAMPLES_DIR, example_name, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        consumer_name = EXAMPLE_SPECS[example_name]["consumer"]
        consumer = data["services"][consumer_name]

        # Must depend on torproxy health
        depends_on = consumer.get("depends_on", {})
        assert "torproxy" in depends_on, f"{consumer_name} must depend on torproxy"
        cond = depends_on["torproxy"].get("condition")
        err = f"{consumer_name} must wait for torproxy condition: service_healthy"
        assert cond == "service_healthy", err

        # All published ports must bind strictly to 127.0.0.1
        ports = consumer.get("ports", [])
        assert ports, f"{consumer_name} has no published ports defined"
        for port_spec in ports:
            assert port_spec.startswith("127.0.0.1:"), (
                f"Unsafe port binding in {example_name} ({consumer_name}): '{port_spec}'. "
                "Must bind strictly to 127.0.0.1."
            )

    def test_browserless_proxy_configuration(self):
        compose_path = os.path.join(
            EXAMPLES_DIR, "browserless-chromium-via-tor", "docker-compose.yml"
        )
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        env = data["services"]["browserless"].get("environment", [])
        launch_arg_entry = next((e for e in env if "DEFAULT_LAUNCH_ARGS" in e), None)
        assert launch_arg_entry is not None, "Missing DEFAULT_LAUNCH_ARGS in browserless"
        assert "--proxy-server=http://torproxy:8118" in launch_arg_entry

    def test_crw_proxy_configuration(self):
        compose_path = os.path.join(EXAMPLES_DIR, "crw-web-scraper-via-tor", "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        env = data["services"]["crw"].get("environment", {})
        proxy = env.get("CRW_CRAWLER__PROXY")
        assert proxy == "http://torproxy:8118"

    def test_searxng_proxy_configuration(self):
        settings_path = os.path.join(EXAMPLES_DIR, "searxng-via-tor", "settings.yml")
        assert os.path.exists(settings_path)
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)

        outgoing = settings.get("outgoing", {})
        assert outgoing.get("using_tor_proxy") is True
        proxies = outgoing.get("proxies", {})
        all_proxies = proxies.get("all://", [])
        assert "http://torproxy:8118" in all_proxies

    @pytest.mark.parametrize("example_name", list(EXAMPLE_SPECS.keys()))
    def test_example_readme_documentation(self, example_name):
        readme_path = os.path.join(EXAMPLES_DIR, example_name, "README.md")
        assert os.path.exists(readme_path), f"Missing README.md in {example_name}"
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must have essential sections
        assert "## Architecture" in content or "## Architecture:" in content
        assert "## Prerequisites" in content
        assert "## Quick start" in content or "## Quick start:" in content
        assert "docker compose down" in content
        assert "curl" in content


@pytest.mark.unit
class TestHardenedProductionExample:
    """Validate hardened production compose configuration and documentation."""

    def test_hardened_compose_structure(self):
        compose_path = os.path.join(EXAMPLES_DIR, "hardened-production", "docker-compose.yml")
        assert os.path.exists(compose_path), "Missing hardened-production docker-compose.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "services" in data
        assert "torproxy" in data["services"]
        svc = data["services"]["torproxy"]
        assert svc["image"] == "hapheus/torproxy:latest"
        assert svc["security_opt"] == ["no-new-privileges:true"]
        assert svc["cap_drop"] == ["ALL"]

        # Check strict localhost port binding
        for port_spec in svc["ports"]:
            assert port_spec.startswith("127.0.0.1:"), f"Unsafe port binding: {port_spec}"

    def test_hardened_readme_documentation(self):
        readme_path = os.path.join(EXAMPLES_DIR, "hardened-production", "README.md")
        assert os.path.exists(readme_path), "Missing hardened-production README.md"
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "## Architecture" in content
        assert "## Prerequisites" in content
        assert "## Quick start" in content
        assert "docker compose down" in content
        assert "curl" in content


@pytest.mark.unit
class TestMacOSChromeExample:
    """Validate macOS Chrome incognito example compose, script, and documentation."""

    def test_macos_chrome_compose_structure(self):
        compose_path = os.path.join(EXAMPLES_DIR, "macos-chrome-via-tor", "docker-compose.yml")
        assert os.path.exists(compose_path), "Missing macos-chrome-via-tor docker-compose.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "services" in data
        assert "torproxy" in data["services"]
        svc = data["services"]["torproxy"]
        assert svc["image"] == "hapheus/torproxy:latest"

        # Check strict localhost port binding
        ports = svc.get("ports", [])
        assert ports, "macos-chrome-via-tor torproxy service has no ports defined"
        for port_spec in ports:
            assert port_spec.startswith("127.0.0.1:"), f"Unsafe port binding: {port_spec}"

    def test_open_chrome_script_integrity(self):
        script_path = os.path.join(EXAMPLES_DIR, "macos-chrome-via-tor", "open-chrome.sh")
        assert os.path.exists(script_path), "Missing open-chrome.sh"
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "--incognito" in content
        assert "--proxy-server=" in content
        assert "open -na" in content

    def test_macos_chrome_readme_documentation(self):
        readme_path = os.path.join(EXAMPLES_DIR, "macos-chrome-via-tor", "README.md")
        assert os.path.exists(readme_path), "Missing macos-chrome-via-tor README.md"
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "## Architecture" in content
        assert "## Prerequisites" in content
        assert "## Quick start" in content
        assert "docker compose down" in content
        assert "curl" in content
