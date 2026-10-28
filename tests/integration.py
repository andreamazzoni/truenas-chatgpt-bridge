#!/usr/bin/env python3
"""Offline Docker integration; isolated Compose project, no real NAS/tunnel.

Requires Docker and host openssl. Uses only local images, internal networking.
"""
import importlib.util
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("operations", ROOT / "scripts/bridge.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def run(args, **kw):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def main():
    image = os.environ.get("BRIDGE_TEST_IMAGE", "truenas-chatgpt-bridge:0.1.0")
    legacy_image = os.environ.get("BRIDGE_TEST_LEGACY_IMAGE")
    token = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="bridge-offline-") as tmp:
        folder = Path(tmp)
        for name in ("config/local", "secrets", "tests", ".local"):
            (folder / name).mkdir(parents=True)
        for name in ("fixture.py", "start.py"):
            shutil.copyfile(ROOT / "tests" / name, folder / "tests" / name)
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", str(folder / "tests/server.key"), "-out", str(folder / "config/local/truenas-ca.pem")])
        for name in ("openai_api_key", "truenas_api_key"):
            path = folder / "secrets" / name
            path.write_text("fixture-" + token + "\n")
            path.chmod(0o600)
        cfg = dict(truenas_api_user="fixture-user", truenas_host="127.0.0.1:9443", tunnel_id="tunnel_" + "a" * 32, ca_file="truenas-ca.pem", organization_id="")
        if legacy_image:
            del cfg["truenas_api_user"]
        (folder / "config/local/settings.json").write_text(json.dumps(cfg))
        (folder / ".env").write_text(f"BRIDGE_IMAGE={legacy_image or image}\nBRIDGE_UID={os.getuid()}\nBRIDGE_GID={os.getgid()}\n")
        # Same production hardening/secrets/health, with a test entrypoint and
        # internal-only network. No endpoint can reach OpenAI or the real NAS.
        source = (ROOT / "compose.yaml").read_text()
        source = source.replace("name: truenas-chatgpt-bridge", "name: bridge-offline-" + token[:8])
        source = source.replace("    pull_policy: never", '    entrypoint: [python, /tests/start.py]\n    networks: [offline]\n    pull_policy: never')
        source = source.replace("    secrets:\n", "      - type: bind\n        source: ./tests\n        target: /tests\n        read_only: true\n    secrets:\n", 1)
        source = source.replace("interval: 60s", "interval: 3s").replace("start_period: 45s", "start_period: 3s")
        source += "\nnetworks:\n  offline:\n    internal: true\n"
        (folder / "compose.yaml").write_text(source)
        ops.ROOT = folder
        ops.LOCAL = folder / ".local"
        try:
            ops.compose("config", "--quiet")
            ops.compose("up", "-d", "--no-build", "--pull", "never")
            ops.wait_healthy()
            print("PASS: native container, TLS, official MCP initialize/list/system_info, tunnel polling and health")
            for command in ("status", "probe"):
                with redirect_stdout(io.StringIO()) as output:
                    assert ops.show_report(command) == 0
                assert "OpenAI tunnel: connected" in output.getvalue()
                assert "ChatGPT call: not verified" in output.getvalue()
                with redirect_stdout(io.StringIO()) as output:
                    assert ops.show_report(command, json_output=True) == 0
                report = json.loads(output.getvalue())
                assert report["tunnel_ready"] and report["nas_probe"]["ok"]
            print("PASS: readable status/probe and original JSON reports")
            cid = ops.compose("ps", "-q", "bridge", capture=True).stdout.strip()
            before = json.loads(ops.execute(["docker", "inspect", cid], capture=True).stdout)[0]
            assert before["HostConfig"]["ReadonlyRootfs"]
            assert before["HostConfig"]["CapDrop"] == ["ALL"]
            assert not before["HostConfig"]["Privileged"]
            assert not before["HostConfig"]["PortBindings"]
            assert before["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
            assert all(m["Destination"] != "/var/run/docker.sock" for m in before["Mounts"])
            ops.compose("exec", "-T", "bridge", "test", "-f", "/tmp/stdio-verified")
            ops.compose("restart", "bridge")
            ops.wait_healthy()
            after = json.loads(ops.execute(["docker", "inspect", cid], capture=True).stdout)[0]
            assert before["State"]["StartedAt"] != after["State"]["StartedAt"]
            assert after["State"]["ExitCode"] != 137
            print("PASS: container restart and graceful stop/start")
            # Real rollback path used by the host CLI, retaining the exact image.
            previous = ops.active_image()
            # Candidate image has a distinct config ID without altering software.
            candidate = "truenas-chatgpt-bridge:offline-candidate-" + token[:8]
            build = subprocess.run(["docker", "build", "--network=none", "-t", candidate, "-"], input=f"FROM {image}\nLABEL bridge.offline.fixture={token[:8]}\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert build.returncode == 0, "Candidate image build failed"
            sys.argv = ["bridge.py", "update", "--image", candidate, "--api-user", "fixture-user"]
            ops.main()
            migrated = json.loads((folder / "config/local/settings.json").read_text())
            assert migrated["truenas_api_user"] == "fixture-user"
            # The new official stdio server must work with JSON-RPC login.
            ops.compose("exec", "-T", "bridge", "test", "-f", "/tmp/stdio-verified")
            sys.argv = ["bridge.py", "rollback"]
            ops.main()
            assert ops.active_image() == previous
            assert json.loads((folder / "config/local/settings.json").read_text()) == cfg
            ops.select_image(previous)
            assert "BRIDGE_IMAGE=" + previous in (folder / ".env").read_text()
            print("PASS: candidate replacement and rollback to retained exact image")
            if legacy_image:
                print("PASS: real 0.0.6 -> 0.0.7 migration and rollback restore both image and legacy configuration")
            logs = ops.compose("logs", "--no-color", capture=True).stdout
            assert token not in logs, "Fixture credential appeared in logs"
            assert token not in json.dumps(before["Config"]), "Fixture credential appeared in container configuration"
            ops.compose("stop", "bridge")
            stopped = json.loads(ops.execute(["docker", "inspect", ops.compose("ps", "-aq", "bridge", capture=True).stdout.strip()], capture=True).stdout)[0]
            assert stopped["State"]["ExitCode"] == 0, "Graceful tunnel shutdown failed"
            print("PASS: no credential in logs/config, tunnel shutdown exit 0")
            # Reset only this temporary project, with fake secrets. Preserve
            # the code and local images, and exercise a second reset as well.
            sys.argv = ["bridge.py", "reset"]
            with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stderr, "isatty", return_value=True), patch("builtins.input", return_value="RESET"):
                ops.main()
                ops.main()
            for name in (".env", "config/local", "secrets", ".local"):
                assert not (folder / name).exists(), "Reset left private local state"
            assert (folder / "compose.yaml").is_file()
            run(["docker", "image", "inspect", previous])
            print("PASS: confirmed reset removes project resources and private files, preserves code/images, and can be repeated")
        except Exception:
            logs = ops.compose("logs", "--no-color", capture=True, check=False).stdout
            print(logs.replace(token, "[FIXTURE-REDACTED]")[-12000:], file=sys.stderr)
            raise
        finally:
            ops.compose("down", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
