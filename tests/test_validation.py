import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from config import ConfigError, endpoint, secret, settings
import runtime


class ValidationTests(unittest.TestCase):
    def test_host_rejects_credential_leak_and_http(self):
        for host in ("https://nas.example", "http://nas", "ws://nas", "user:pass@nas", "nas/path", "nas?key=abc", "nas\n", "nas:0", "nas:65536", "-bad.example", "999.999.1.1", "::1", "nas%00"):
            with self.subTest(host=host), self.assertRaises((ConfigError, ValueError)):
                endpoint(host)

    def test_dns_ipv4_ipv6_and_custom_port(self):
        for host, expected in (("nas.example", ("nas.example", 443)), ("192.0.2.1:8443", ("192.0.2.1", 8443)), ("[2001:db8::1]:8443", ("2001:db8::1", 8443))):
            self.assertEqual(endpoint(host), expected)

    def test_private_credentials_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_text("fixture-token\n")
            path.chmod(0o600)
            self.assertEqual(secret(path), "fixture-token")
            path.chmod(0o644)
            with self.assertRaises(ConfigError):
                secret(path)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(ConfigError):
                secret(link)

    def test_settings_rejects_unknown_fields_and_command_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            cfg = dict(truenas_host="nas.example", tunnel_id="tunnel_" + "a" * 32, ca_file="", organization_id="")
            path.write_text(json.dumps(cfg))
            self.assertEqual(settings(path), cfg)
            for field, value in (("ca_file", "../../key"), ("tunnel_id", "tunnel_bad\n"), ("organization_id", "org-x\n"), ("command", "echo")):
                altered = cfg | {field: value}
                path.write_text(json.dumps(altered))
                with self.assertRaises(ConfigError):
                    settings(path)

    def test_readiness_needs_recent_successful_poll(self):
        def run(stamp):
            def get(path):
                return (200, f"commands_poll_last_successful_timestamp_seconds {stamp}\n") if path == "/metrics" else (200, "live")
            with patch.object(runtime, "get", get):
                return runtime.tunnel_status()
        self.assertFalse(run(0)["tunnel_ready"])
        self.assertFalse(run(time.time() - 300)["tunnel_ready"])
        self.assertTrue(run(time.time())["tunnel_ready"])
        self.assertFalse(run("NaN")["tunnel_ready"])

    def test_mcp_environment_contains_no_tunnel_key_or_insecure_flags(self):
        with patch.object(runtime, "secret", return_value="fixture-token"):
            env = runtime.nas_environment({"truenas_host": "nas.example:8443", "ca_file": ""})
        self.assertEqual(env["TRUENAS_URL"], "wss://nas.example:8443/websocket")
        self.assertEqual(set(env), {"PATH", "HOME", "TRUENAS_URL", "TRUENAS_API_KEY"})


if __name__ == "__main__":
    unittest.main()
