"""Status semantics and CLI compatibility; no real Docker or NAS calls."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("status_operations", Path(__file__).resolve().parents[1] / "scripts/bridge.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.report = {"process_live": True, "startup_ready": True,
                       "tunnel_ready": True, "poll_age_seconds": 3.5,
                       "nas_probe": {"ok": True, "checked_at": 1700000000,
                                     "method": "system.info", "path": "official-client-separate-session"}}

    def test_saved_success_is_not_presented_as_current_nas_or_chatgpt_success(self):
        with patch.object(ops.time, "time", return_value=1700000600):
            text = ops.readable_report(self.report, "status")
        self.assertIn("OpenAI tunnel: connected", text)
        self.assertIn("NAS last saved read check: succeeded", text)
        self.assertIn("2023-11-14 22:13:20 UTC (600 seconds ago)", text)
        self.assertIn("status does not contact the NAS", text)
        self.assertIn("ChatGPT call: not verified", text)

    def test_no_probe_and_no_poll_do_not_look_successful(self):
        self.report.update(tunnel_ready=False, poll_age_seconds=None, nas_probe=None)
        text = ops.readable_report(self.report, "status")
        self.assertIn("no successful polling observed", text)
        self.assertIn("NAS: no saved check", text)

    def test_stale_poll_does_not_hide_successful_nas_probe(self):
        self.report.update(tunnel_ready=False, poll_age_seconds=300)
        text = ops.readable_report(self.report, "probe")
        self.assertIn("OpenAI tunnel: not ready", text)
        self.assertIn("300 seconds ago", text)
        self.assertIn("NAS read check: succeeded", text)
        self.assertNotIn("NAS last saved", text)

    def test_failed_nas_probe_still_prints_report_and_returns_failure(self):
        self.report["nas_probe"]["ok"] = False
        payload = json.dumps(self.report) + "\n"
        with patch.object(ops, "compose", side_effect=[subprocess.CompletedProcess([], 0, "fixture-id"), subprocess.CompletedProcess([], 1, payload)]) as compose, \
             patch.object(ops, "execute", return_value=subprocess.CompletedProcess([], 0, "running\n")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ops.show_report("probe"), 1)
        self.assertIn("NAS read check: failed", output.getvalue())
        self.assertEqual(compose.call_args.args[-1], "probe")

    def test_json_preserves_original_output_and_exit_code_without_extra_docker_calls(self):
        payload = json.dumps(self.report, indent=2) + "\n"
        for command, code in (("status", 0), ("probe", 1)):
            with self.subTest(command=command), patch.object(ops, "compose", return_value=subprocess.CompletedProcess([], code, payload)) as compose, \
                 patch.object(ops, "execute") as execute, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(ops.show_report(command, json_output=True), code)
                self.assertEqual(output.getvalue(), payload)
                execute.assert_not_called()
                compose.assert_called_once_with("exec", "-T", "bridge", "python", "/opt/bridge/runtime.py", command, capture=True, check=False)

    def test_status_uses_only_status_runtime_command(self):
        with patch.object(ops, "compose", side_effect=[subprocess.CompletedProcess([], 0, "fixture-id"), subprocess.CompletedProcess([], 0, json.dumps(self.report))]) as compose, \
             patch.object(ops, "execute", return_value=subprocess.CompletedProcess([], 0, "running\n")), redirect_stdout(io.StringIO()):
            self.assertEqual(ops.show_report("status"), 0)
        self.assertEqual(compose.call_args.args[-1], "status")

    def test_stopped_and_absent_containers_are_reported_without_exec_or_probe(self):
        for cid, state, expected in (("fixture-id", "exited", "stopped"), ("", "", "not installed")):
            with self.subTest(state=state), patch.object(ops, "compose", return_value=subprocess.CompletedProcess([], 0, cid)) as compose, \
                 patch.object(ops, "execute", return_value=subprocess.CompletedProcess([], 0, state)), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(ops.show_report("status"), 1)
                self.assertIn("Container: " + expected, output.getvalue())
                self.assertIn("Tunnel and NAS: not checked", output.getvalue())
                compose.assert_called_once_with("ps", "-aq", "bridge", capture=True)

    def test_invalid_runtime_output_is_not_echoed(self):
        with patch.object(ops, "compose", side_effect=[subprocess.CompletedProcess([], 0, "fixture-id"), subprocess.CompletedProcess([], 1, "private fixture error")]), \
             patch.object(ops, "execute", return_value=subprocess.CompletedProcess([], 0, "running\n")), redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, "status unavailable"):
                ops.show_report("status")
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
