"""Destructive reset is exercised only against temporary checkout fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("reset_operations", Path(__file__).resolve().parents[1] / "scripts/bridge.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class ResetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.targets = [self.root / name for name in (".env", "config/local", "secrets", ".local")]
        for folder in self.targets[1:]:
            folder.mkdir(parents=True)
            (folder / "fixture").write_text("fixture-only")
        self.targets[0].write_text("COMPOSE_PROJECT_NAME=fixture-reset\n")
        (self.root / "README.md").write_text("keep code")
        (self.root / ".git").mkdir()
        self.events = []
        self.answer = "RESET"
        self.fail_down = False
        self.remaining = False
        self.foreign = False
        self.down = False

        def compose(*args, **kwargs):
            self.events.append(args)
            if args == ("config", "--format", "json"):
                return subprocess.CompletedProcess(args, 0, json.dumps({"name": "fixture-reset"}))
            self.assertEqual(args, ("down", "--remove-orphans"))
            if not self.down:
                self.assertTrue(all(path.exists() for path in self.targets))
            if self.fail_down:
                raise subprocess.CalledProcessError(1, args)
            self.down = True

        def execute(args, **kwargs):
            self.events.append(tuple(args))
            if args[1] == "inspect":
                output = json.dumps({
                    "com.docker.compose.project.working_dir": "/another/checkout" if self.foreign else str(self.root),
                    "com.docker.compose.project.config_files": str(self.root / "compose.yaml"),
                })
            elif args[1] == "ps":
                output = "fixture-container" if not self.down or self.remaining else ""
            else:
                self.assertEqual(args[1:4], ["network", "ls", "-q"])
                output = "fixture-network" if self.remaining else ""
            return subprocess.CompletedProcess(args, 0, output)

        for context in (
            patch.object(ops, "ROOT", self.root),
            patch.object(ops, "LOCAL", self.root / ".local"),
            patch.object(ops.sys.stdin, "isatty", return_value=True),
            patch.object(ops.sys.stderr, "isatty", return_value=True),
            patch.object(ops.os, "getuid", return_value=1000),
            patch.object(ops, "compose", side_effect=compose),
            patch.object(ops, "execute", side_effect=execute),
            patch("builtins.input", side_effect=lambda _: self.answer),
            patch("builtins.print"),
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_cleanup_preserves_code_git_and_external_symlink_targets(self):
        (self.root / "secrets/external-link").symlink_to(self.root / "README.md")
        with patch.object(ops.sys, "argv", ["bridge.py", "reset"]):
            ops.main()
        self.assertTrue(self.down)
        self.assertFalse(any(path.exists() for path in self.targets))
        self.assertEqual((self.root / "README.md").read_text(), "keep code")
        self.assertTrue((self.root / ".git").is_dir())
        self.assertFalse(any(event[:3] == ("docker", "image", "rm") for event in self.events))

    def test_declining_or_lowercase_confirmation_keeps_everything(self):
        for answer in ("no", "reset", ""):
            self.answer = answer
            ops.reset()
            self.assertFalse(self.down)
            self.assertTrue(all(path.exists() for path in self.targets))

    def test_docker_failure_keeps_all_local_files(self):
        self.fail_down = True
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            ops.reset()
        self.assertTrue(all(path.exists() for path in self.targets))

    def test_interrupted_confirmation_keeps_everything(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ops.reset()
        self.assertFalse(self.down)
        self.assertTrue(all(path.exists() for path in self.targets))

    def test_filesystem_failure_keeps_project_selection_for_retry(self):
        with patch.object(ops.shutil, "rmtree", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                ops.reset()
        self.assertTrue((self.root / ".env").exists())
        ops.reset()
        self.assertFalse(any(path.exists() for path in self.targets))

    def test_remaining_resources_keep_all_local_files(self):
        self.remaining = True
        with self.assertRaisesRegex(RuntimeError, "resources remain"):
            ops.reset()
        self.assertTrue(all(path.exists() for path in self.targets))

    def test_other_checkout_with_same_project_name_is_not_removed(self):
        self.foreign = True
        with self.assertRaisesRegex(RuntimeError, "another checkout"):
            ops.reset()
        self.assertFalse(self.down)
        self.assertTrue(all(path.exists() for path in self.targets))

    def test_symlinked_configuration_parent_is_rejected_before_docker(self):
        (self.root / "config").rename(self.root / "outside-config")
        (self.root / "config").symlink_to(self.root / "outside-config", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlinks"):
            ops.reset()
        self.assertEqual(self.events, [])
        self.assertTrue((self.root / "outside-config/local/fixture").exists())

    def test_noninteractive_and_root_are_rejected(self):
        with patch.object(ops.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                ops.reset()
        with patch.object(ops.os, "getuid", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "non-root"):
                ops.reset()
        self.assertEqual(self.events, [])

    def test_checkout_lock_survives_removal_of_local_directory(self):
        with ops.checkout_lock():
            ops.shutil.rmtree(self.root / ".local")
            with self.assertRaises(BlockingIOError):
                with ops.checkout_lock():
                    self.fail("Concurrent operation obtained checkout lock")

    def test_repeating_reset_with_missing_local_files_is_safe(self):
        ops.reset()
        ops.reset()
        self.assertFalse(any(path.exists() for path in self.targets))


if __name__ == "__main__":
    unittest.main()
