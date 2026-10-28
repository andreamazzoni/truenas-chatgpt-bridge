"""Configuration/image replacement order, using temporary files and fake Docker."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("migration_operations", Path(__file__).resolve().parents[1] / "scripts/bridge.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / ".local"
        self.local.mkdir()
        self.directory = self.root / "config/local"
        self.directory.mkdir(parents=True)
        self.path = self.directory / "settings.json"
        self.original = dict(truenas_host="nas.example", tunnel_id="tunnel_" + "a" * 32, ca_file="", organization_id="")
        self.path.write_text(json.dumps(self.original))
        self.events = []
        self.fail_preflight = False

        def compose(*args, **kwargs):
            self.events.append((args[0], self.read_settings()))
            if args[0] == "run":
                self.assertIn("--volume", args)
                stage = Path(args[args.index("--volume") + 1].removesuffix(":/etc/bridge:ro"))
                cfg = json.loads((stage / "settings.json").read_text())
                if kwargs["image"] == "sha256:new":
                    self.assertEqual(cfg["truenas_api_user"], "fixture-user")
                else:
                    self.assertEqual(cfg, self.original)
                if self.fail_preflight:
                    raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, "")

        def execute(args, **kwargs):
            if args[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": "sha256:new"}]))
            return subprocess.CompletedProcess(args, 0, "")

        for context in (
            patch.object(ops, "ROOT", self.root), patch.object(ops, "LOCAL", self.local),
            patch.object(ops, "active_image", return_value="sha256:old"),
            patch.object(ops, "execute", side_effect=execute), patch.object(ops, "compose", side_effect=compose),
            patch.object(ops, "wait_healthy"), patch("builtins.print"),
        ):
            context.start()
            self.addCleanup(context.stop)

    def read_settings(self):
        return json.loads(self.path.read_text())

    def update(self):
        with patch.object(ops.sys, "argv", ["bridge.py", "update", "--image", "fixture:candidate", "--api-user", "fixture-user"]):
            ops.main()

    def rollback(self):
        with patch.object(ops.sys, "argv", ["bridge.py", "rollback"]):
            ops.main()

    def test_update_stages_config_and_rollback_restores_exact_legacy_schema(self):
        self.update()
        self.assertEqual([event[0] for event in self.events], ["run", "stop", "up"])
        self.assertEqual(self.events[0][1], self.original)
        self.assertEqual(self.events[1][1], self.original)
        self.assertEqual(self.events[2][1]["truenas_api_user"], "fixture-user")
        saved = json.loads((self.local / "rollback.json").read_text())
        self.assertEqual(saved["configuration"]["settings"], self.original)
        self.assertEqual((self.local / "rollback.json").stat().st_mode & 0o777, 0o600)
        self.rollback()
        self.assertEqual(self.read_settings(), self.original)
        self.assertIn("BRIDGE_IMAGE=sha256:old", (self.root / ".env").read_text())

    def test_failed_preflight_keeps_baseline_and_does_not_stop_tunnel(self):
        self.fail_preflight = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.update()
        self.assertEqual(self.read_settings(), self.original)
        self.assertEqual([event[0] for event in self.events], ["run"])
        self.assertFalse((self.local / "rollback.json").exists())

    def test_failed_candidate_health_still_allows_rollback(self):
        with patch.object(ops, "wait_healthy", side_effect=RuntimeError("fixture health failure")):
            with self.assertRaises(RuntimeError):
                self.update()
        self.rollback()
        self.assertEqual(self.read_settings(), self.original)

    def test_rollback_without_snapshot_refuses_before_stop(self):
        (self.local / "rollback.json").write_text(json.dumps({"id": "sha256:old"}))
        with self.assertRaisesRegex(RuntimeError, "no configuration snapshot"):
            self.rollback()
        self.assertEqual(self.events, [])

    def test_invalid_username_never_stops_or_rewrites_config(self):
        with patch.object(ops.sys, "argv", ["bridge.py", "update", "--image", "fixture:candidate", "--api-user", "invalid\nuser"]):
            with self.assertRaises(ops.ConfigError):
                ops.main()
        self.assertEqual(self.events, [])
        self.assertEqual(self.read_settings(), self.original)

    def test_snapshot_retains_selected_public_ca(self):
        self.original["ca_file"] = "truenas-ca.pem"
        self.path.write_text(json.dumps(self.original))
        (self.directory / "truenas-ca.pem").write_text("fixture-public-certificate")
        self.update()
        (self.directory / "truenas-ca.pem").write_text("changed-fixture-certificate")
        self.rollback()
        self.assertEqual((self.directory / "truenas-ca.pem").read_text(), "fixture-public-certificate")


if __name__ == "__main__":
    unittest.main()
