"""First-install orchestration with fake Docker calls, never real credentials."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_operations", ROOT / "scripts/bridge.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
setup_spec = importlib.util.spec_from_file_location("install_setup", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(setup_spec)
setup_spec.loader.exec_module(setup)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.existing = ""
        self.fail = None
        self.answer = "yes"

        def compose(*args, **kwargs):
            self.events.append(args)
            if args == self.fail:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, self.existing if args == ("ps", "-aq", "bridge") else "")

        def execute(args, **kwargs):
            self.events.append(tuple(args))

        def confirm(_):
            self.events.append(("confirm",))
            return self.answer

        for context in (
            patch.object(ops.sys.stdin, "isatty", return_value=True),
            patch.object(ops.sys.stderr, "isatty", return_value=True),
            patch.object(ops.os, "getuid", return_value=1000),
            patch.object(ops, "compose", side_effect=compose),
            patch.object(ops, "execute", side_effect=execute),
            patch.object(ops, "wait_healthy", side_effect=lambda: self.events.append(("healthy",))),
            patch("builtins.input", side_effect=confirm),
            patch("builtins.print"),
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_validates_and_confirms_before_starting(self):
        ops.install()
        validate = self.events.index(("run", "--rm", "--no-deps", "bridge", "validate"))
        confirm = self.events.index(("confirm",))
        start = self.events.index(("up", "-d", "--no-build", "--pull", "never", "bridge"))
        self.assertLess(validate, confirm)
        self.assertLess(confirm, start)
        self.assertEqual(self.events[-1], ("healthy",))

    def test_existing_stopped_or_running_container_is_untouched(self):
        self.existing = "fixture-container"
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            ops.install()
        self.assertEqual(self.events[-1], ("ps", "-aq", "bridge"))

    def test_declining_confirmation_does_not_start(self):
        self.answer = "no"
        ops.install()
        self.assertEqual(self.events[-1], ("confirm",))

    def test_failed_build_never_requests_credentials(self):
        self.fail = ("build", "bridge")
        with self.assertRaises(subprocess.CalledProcessError):
            ops.install()
        self.assertEqual(self.events[-1], self.fail)

    def test_failed_validation_never_confirms_or_starts(self):
        self.fail = ("run", "--rm", "--no-deps", "bridge", "validate")
        with self.assertRaises(subprocess.CalledProcessError):
            ops.install()
        self.assertEqual(self.events[-1], self.fail)

    def test_requires_interactive_non_root_operator(self):
        with patch.object(ops.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                ops.install()
        with patch.object(ops.os, "getuid", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "non-root"):
                ops.install()
        self.assertEqual(self.events, [])


class ResumeSetupTests(unittest.TestCase):
    def test_interrupted_secret_input_preserves_settings_and_completed_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answers = ["nas.example", "tunnel_" + "a" * 32, "", ""]
            with patch.object(setup, "ROOT", root), patch.object(setup.sys, "argv", ["setup.py"]), \
                 patch.object(setup.sys.stdin, "isatty", return_value=True), \
                 patch.object(setup.sys.stderr, "isatty", return_value=True), \
                 patch.object(setup.os, "getuid", return_value=1000), \
                 patch.object(setup.os, "umask"), patch.object(setup, "tls_check"), \
                 patch("builtins.print"), patch("builtins.input", side_effect=answers), \
                 patch.object(setup.getpass, "getpass", side_effect=["fixture-openai", KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    setup.main()
            cfg = json.loads((root / "config/local/settings.json").read_text())
            self.assertEqual(cfg["truenas_host"], "nas.example")
            first_key = root / "secrets/openai_api_key"
            first_inode = first_key.stat().st_ino
            with patch.object(setup, "ROOT", root), patch.object(setup.sys, "argv", ["setup.py"]), \
                 patch.object(setup.sys.stdin, "isatty", return_value=True), \
                 patch.object(setup.sys.stderr, "isatty", return_value=True), \
                 patch.object(setup.os, "getuid", return_value=1000), \
                 patch.object(setup.os, "umask"), patch.object(setup, "tls_check"), \
                 patch("builtins.print"), patch("builtins.input", side_effect=["", "", "", ""]), \
                 patch.object(setup.getpass, "getpass", return_value="fixture-nas") as hidden:
                setup.main()
            self.assertEqual(hidden.call_count, 1)
            self.assertEqual(first_key.stat().st_ino, first_inode)
            self.assertEqual(json.loads((root / "config/local/settings.json").read_text()), cfg)
            self.assertTrue((root / ".env").is_file())


if __name__ == "__main__":
    unittest.main()
