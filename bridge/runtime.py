"""File-backed startup and bounded health probes. Never print secret values."""
import json
import math
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

from config import ConfigError, endpoint, secret, settings, tls_check

DIRECTORY = Path("/etc/bridge")
STATE = Path("/tmp/nas-probe.json")
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def nas_environment(cfg):
    # Explicit allowlist prevents tunnel credentials or debug/insecure flags
    # from reaching the MCP child. The API key is never an argv value.
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/home"}
    host, port = endpoint(cfg["truenas_host"])
    authority = f"[{host}]" if ":" in host else host
    # v0.0.6 drops custom ports from bare hostnames; use its supported wss URL.
    env["TRUENAS_URL"] = f"wss://{authority}:{port}/websocket"
    env["TRUENAS_API_KEY"] = secret("/run/secrets/truenas_api_key")
    if cfg["ca_file"]:
        env["TRUENAS_TLS_CA"] = str(DIRECTORY / cfg["ca_file"])
    return env


def get(path):
    try:
        with HTTP.open("http://127.0.0.1:8080" + path, timeout=2) as response:
            return response.status, response.read(1024 * 1024).decode()
    except (OSError, urllib.error.URLError):
        return 0, ""


def tunnel_status():
    live = get("/healthz")[0] == 200
    ready = get("/readyz")[0] == 200
    code, metrics = get("/metrics")
    match = re.search(r"^commands_poll_last_successful_timestamp_seconds(?:\{[^\n]*\})? ([^\n ]+)", metrics, re.M)
    age = None
    if code == 200 and match:
        stamp = float(match[1])
        if math.isfinite(stamp) and stamp > 0:
            age = max(0, time.time() - stamp)
    return {"process_live": live, "startup_ready": ready,
            "tunnel_ready": live and ready and age is not None and age <= 120,
            "poll_age_seconds": round(age, 1) if age is not None else None}


def probe(cfg):
    ok = False
    try:
        tls_check(cfg, DIRECTORY)
        ok = subprocess.run(["/usr/local/bin/bridge-probe"], env=nas_environment(cfg),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=20, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired, ConfigError):
        pass
    result = {"ok": ok, "checked_at": int(time.time()), "method": "system.info",
              "path": "official-client-separate-session"}
    temporary = STATE.with_suffix(".new")
    temporary.write_text(json.dumps(result) + "\n")
    temporary.replace(STATE)
    return result


def main():
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "status":
        report = tunnel_status()
        report["nas_probe"] = json.loads(STATE.read_text()) if STATE.exists() else None
        print(json.dumps(report, sort_keys=True))
        return 0
    cfg = settings(DIRECTORY / "settings.json")
    if command in ("run", "mcp", "validate"):
        secret("/run/secrets/truenas_api_key", read=False)
        secret("/run/secrets/openai_api_key", read=False)
        tls_check(cfg, DIRECTORY)
        if command == "validate":
            print("Configuration, credential file permissions and verified TLS: OK")
            return 0
        if command == "mcp":
            os.execve("/usr/local/bin/truenas-mcp", ["truenas-mcp"], nas_environment(cfg))
        Path("/tmp/home").mkdir(mode=0o700, exist_ok=True)
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/home",
               "CONTROL_PLANE_TUNNEL_ID": cfg["tunnel_id"],
               "CONTROL_PLANE_API_KEY": "file:/run/secrets/openai_api_key",
               "MCP_COMMAND": "python /opt/bridge/runtime.py mcp",
               "HEALTH_LISTEN_ADDR": "127.0.0.1:8080",
               "LOG_LEVEL": "info", "LOG_FORMAT": "json"}
        if cfg["organization_id"]:
            env["CONTROL_PLANE_ORGANIZATION_ID"] = cfg["organization_id"]
        os.execve("/usr/local/bin/tunnel-client", ["tunnel-client", "run"], env)
    if command in ("probe", "health"):
        report = tunnel_status()
        report["nas_probe"] = probe(cfg)
        print(json.dumps(report, sort_keys=True))
        return 0 if (report["nas_probe"]["ok"] and (command == "probe" or report["tunnel_ready"])) else 1
    raise ConfigError("Use run, mcp, validate, status, probe or health")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ConfigError, OSError, ValueError, ssl.SSLError):
        # Avoid echoing arbitrary upstream/server error strings or local content.
        print("Bridge check failed; verify local settings, file permissions, DNS and TLS", file=sys.stderr)
        sys.exit(1)
