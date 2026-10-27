from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import runtime


class ProbeTests(unittest.TestCase):
    def test_concurrent_probes_publish_complete_results(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "nas-probe.json"
            previous = {"ok": False, "checked_at": 1}
            state.write_text(json.dumps(previous))
            gate = threading.Barrier(2)
            original_replace = Path.replace
            temporary_paths = []

            def replace(path, target):
                # Both writers finish before either publishes. Readers must
                # still see the previous complete report at this point.
                temporary_paths.append(path)
                self.assertEqual(json.loads(state.read_text()), previous)
                self.assertTrue(json.loads(path.read_text())["ok"])
                gate.wait(timeout=10)
                return original_replace(path, target)

            with patch.object(runtime, "STATE", state), \
                    patch.object(runtime, "tls_check"), \
                    patch.object(runtime, "nas_environment", return_value={}), \
                    patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(Path, "replace", replace):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    probes = [pool.submit(runtime.probe, {}) for _ in range(2)]
                    results = [probe.result(timeout=15) for probe in probes]

            self.assertEqual(len(set(temporary_paths)), 2)
            self.assertTrue(all(result["ok"] for result in results))
            self.assertIn(json.loads(state.read_text()), results)
            self.assertEqual(list(Path(folder).iterdir()), [state])

    def test_failed_publish_preserves_previous_report_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "nas-probe.json"
            previous = {"ok": False, "checked_at": 1}
            state.write_text(json.dumps(previous))
            with patch.object(runtime, "STATE", state), \
                    patch.object(runtime, "tls_check"), \
                    patch.object(runtime, "nas_environment", return_value={}), \
                    patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(Path, "replace", side_effect=OSError("Fixture publish failure")):
                with self.assertRaises(OSError):
                    runtime.probe({})

            self.assertEqual(json.loads(state.read_text()), previous)
            self.assertEqual(list(Path(folder).iterdir()), [state])

    def test_nas_failure_publishes_unsuccessful_report(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "nas-probe.json"
            with patch.object(runtime, "STATE", state), \
                    patch.object(runtime, "tls_check", side_effect=OSError("Fixture TLS failure")), \
                    patch.object(runtime.subprocess, "run") as run:
                result = runtime.probe({})

            run.assert_not_called()
            self.assertFalse(result["ok"])
            self.assertEqual(json.loads(state.read_text()), result)
            self.assertEqual(list(Path(folder).iterdir()), [state])


if __name__ == "__main__":
    unittest.main()
