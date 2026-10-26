"""TEST ONLY: exercise official MCP stdio, then start tunnel with local fixture."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

sys.path.insert(0, "/opt/bridge")
import runtime

subprocess.Popen(["python", "/tests/fixture.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
cfg = runtime.settings("/etc/bridge/settings.json")
for attempt in range(50):
    try:
        runtime.tls_check(cfg, runtime.DIRECTORY)
        break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("Fixture TLS startup failed")

if len(sys.argv) > 1 and sys.argv[1] == "validate":
    sys.argv = ["runtime.py", "validate"]
    raise SystemExit(runtime.main())

with subprocess.Popen(["python", "/opt/bridge/runtime.py", "mcp"], stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as mcp:
    def exchange(message):
        mcp.stdin.write(json.dumps(message) + "\n")
        mcp.stdin.flush()
        if "id" in message:
            if not select.select([mcp.stdout], [], [], 15)[0]:
                raise RuntimeError("Official MCP stdio timed out")
            return json.loads(mcp.stdout.readline())

    reply = exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "offline-fixture", "version": "1"}}})
    assert reply["result"]["serverInfo"]["name"] == "truenas-mcp"
    exchange({"jsonrpc": "2.0", "method": "notifications/initialized"})
    reply = exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert any(tool["name"] == "system_info" for tool in reply["result"]["tools"])
    reply = exchange({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "system_info", "arguments": {}}})
    assert not reply["result"].get("isError")
    assert "FIXTURE" in reply["result"]["content"][0]["text"]
    mcp.stdin.close()
    mcp.wait(timeout=10)
Path("/tmp/stdio-verified").touch()

# Inject a test-only loopback control plane. Production has no such override.
original_exec = os.execve
def fixture_exec(path, argv, env):
    env["CONTROL_PLANE_BASE_URL"] = "http://127.0.0.1:9080"
    original_exec(path, argv, env)
runtime.os.execve = fixture_exec
sys.argv = ["runtime.py", "run"]
runtime.main()
