#!/usr/bin/env python3
"""Host operations. All paths are relative to this checkout, not the shell cwd."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def execute(args, *, capture=False, check=True):
    return subprocess.run(args, cwd=ROOT, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None)


def compose(*args, capture=False, check=True, image=None):
    env = os.environ.copy()
    if image:
        env["BRIDGE_IMAGE"] = image
    return subprocess.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"), *args],
                          cwd=ROOT, env=env, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None)


def wait_healthy():
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        cid = compose("ps", "-q", "bridge", capture=True).stdout.strip()
        if cid:
            state = json.loads(execute(["docker", "inspect", cid], capture=True).stdout)[0]["State"]
            if state.get("Health", {}).get("Status") == "healthy":
                return
        time.sleep(3)
    raise RuntimeError("Bridge did not become healthy within 180s; retained image is available for rollback")


def active_image():
    cid = compose("ps", "-q", "bridge", capture=True).stdout.strip()
    if not cid:
        raise RuntimeError("Start and verify the current deployment before updating")
    item = json.loads(execute(["docker", "inspect", cid], capture=True).stdout)[0]
    if item["State"].get("Health", {}).get("Status") != "healthy":
        raise RuntimeError("Refusing to replace a deployment without a healthy rollback baseline")
    return item["Image"]


def retain(image):
    tag = "truenas-chatgpt-bridge:rollback-" + str(time.time_ns())
    execute(["docker", "image", "tag", image, tag])
    (LOCAL / "rollback.json").write_text(json.dumps({"image": tag, "id": image}) + "\n")
    print("Previous image retained locally: " + tag)


def select_image(image):
    path = ROOT / ".env"
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith("BRIDGE_IMAGE=")]
    lines.append("BRIDGE_IMAGE=" + image)
    fd, temporary = tempfile.mkstemp(dir=ROOT, prefix=".env-")
    with os.fdopen(fd, "w") as stream:
        stream.write("\n".join(lines) + "\n")
    os.replace(temporary, path)
    (LOCAL / "current-image").write_text(image + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "validate", "start", "stop", "status", "probe", "restart", "update", "rollback"])
    parser.add_argument("--image", help="Locally built, unique candidate image tag for update")
    parser.add_argument("--single-instance-confirmed", action="store_true", help="Operator has stopped any previous host using this tunnel")
    args = parser.parse_args()
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    with (LOCAL / "operations.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cmd = args.command
        if cmd == "build":
            compose("build", "bridge")
        elif cmd == "validate":
            execute([sys.executable, str(ROOT / "scripts/setup.py"), "--validate"])
            compose("config", "--quiet")
            compose("run", "--rm", "--no-deps", "bridge", "validate")
        elif cmd == "start":
            if not args.single_instance_confirmed:
                raise RuntimeError("Stop the previous tunnel host, then use --single-instance-confirmed")
            compose("run", "--rm", "--no-deps", "bridge", "validate")
            compose("up", "-d", "--no-build", "--pull", "never", "bridge")
            wait_healthy()
        elif cmd == "stop":
            compose("stop", "bridge")
        elif cmd in ("status", "probe"):
            compose("exec", "-T", "bridge", "python", "/opt/bridge/runtime.py", cmd)
        elif cmd == "restart":
            compose("restart", "bridge")
            wait_healthy()
        elif cmd == "update":
            if not args.image or not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9_.-]+", args.image) or args.image.endswith(":latest"):
                raise RuntimeError("Provide a unique local candidate image tag (no latest)")
            previous = active_image()
            candidate = json.loads(execute(["docker", "image", "inspect", args.image], capture=True).stdout)[0]["Id"]
            if candidate == previous:
                raise RuntimeError("Candidate is the current image")
            compose("run", "--rm", "--no-deps", "bridge", "validate", image=candidate)
            retain(previous)
            compose("stop", "bridge")
            compose("up", "-d", "--force-recreate", "--no-build", "--pull", "never", "bridge", image=candidate)
            wait_healthy()
            # Persist the immutable ID only after successful health verification.
            select_image(candidate)
            print("Update healthy; immutable image selection saved in .env.")
        elif cmd == "rollback":
            saved = json.loads((LOCAL / "rollback.json").read_text())
            execute(["docker", "image", "inspect", saved["id"]], capture=True)
            compose("stop", "bridge")
            compose("up", "-d", "--force-recreate", "--no-build", "--pull", "never", "bridge", image=saved["id"])
            wait_healthy()
            select_image(saved["id"])
            print("Rollback healthy; immutable image selection saved in .env.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error) if isinstance(error, RuntimeError) else "Operation failed; check local files and Docker status", file=sys.stderr)
        sys.exit(1)
