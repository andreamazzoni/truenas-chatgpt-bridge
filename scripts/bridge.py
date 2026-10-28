#!/usr/bin/env python3
"""Host operations. All paths are relative to this checkout, not the shell cwd."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def readable_report(report, command):
    lines = ["Container: running",
             "Tunnel process: " + ("responding" if report["process_live"] else "not responding"),
             "Tunnel startup: " + ("ready" if report["startup_ready"] else "not ready")]
    age = report["poll_age_seconds"]
    if report["tunnel_ready"]:
        tunnel = "connected (recent successful polling)"
    elif age is None:
        tunnel = "not ready (no successful polling observed)"
    else:
        tunnel = "not ready"
    lines.append("OpenAI tunnel: " + tunnel)
    if age is not None:
        lines.append(f"Last successful tunnel poll: {age:.0f} seconds ago")
    nas = report.get("nas_probe")
    if nas is None:
        lines.append("NAS: no saved check; run python3 scripts/bridge.py probe")
    else:
        label = "NAS read check" if command == "probe" else "NAS last saved read check"
        lines.append(label + ": " + ("succeeded" if nas["ok"] else "failed"))
        stamp = nas["checked_at"]
        checked = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        elapsed = max(0, int(time.time() - stamp))
        lines.append(f"NAS checked at: {checked} ({elapsed} seconds ago)")
        if command == "status":
            lines.append("Saved result only; status does not contact the NAS. Run probe for a fresh check.")
    lines.append("ChatGPT call: not verified by this check; test system_info from ChatGPT.")
    return "\n".join(lines)


def show_report(command, *, json_output=False):
    if not json_output:
        cid = compose("ps", "-aq", "bridge", capture=True).stdout.strip()
        state = execute(["docker", "inspect", "--format", "{{.State.Status}}", cid], capture=True).stdout.strip() if cid else None
        if state != "running":
            labels = {None: "not installed", "exited": "stopped", "created": "not started",
                      "restarting": "restarting", "paused": "paused", "dead": "dead", "removing": "being removed"}
            print("Container: " + labels.get(state, "unavailable"))
            print("Tunnel and NAS: not checked; the bridge must be running.")
            print("ChatGPT call: not verified by this check.")
            return 1
    result = compose("exec", "-T", "bridge", "python", "/opt/bridge/runtime.py", command,
                     capture=True, check=False)
    if json_output:
        # Keep the runtime's original JSON and exit code for existing scripts.
        sys.stdout.write(result.stdout)
    else:
        try:
            print(readable_report(json.loads(result.stdout), command))
        except (ValueError, KeyError, TypeError, OverflowError, OSError):
            raise RuntimeError("Bridge status unavailable; check that the container is running and retry.") from None
    return result.returncode


@contextmanager
def checkout_lock():
    # Lock the checkout inode: reset can remove .local without making a second
    # lock file available to another concurrent operation.
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


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
            if state.get("Restarting") or state.get("Status") in ("exited", "dead"):
                raise RuntimeError("Bridge exited during startup; inspect bounded logs before retrying")
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


def install():
    """First installation only; reuse build cache and saved setup on retries."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError("Install requires a local interactive terminal with hidden input")
    if os.getuid() == 0:
        raise RuntimeError("Run install as the non-root user who will operate Compose")
    print("Checking Docker and Compose...", flush=True)
    execute(["docker", "info"], capture=True)
    execute(["docker", "compose", "version"], capture=True)
    execute(["docker", "buildx", "version"], capture=True)
    if compose("ps", "-aq", "bridge", capture=True).stdout.strip():
        raise RuntimeError("A bridge container already exists. Use status, start, restart or update to manage it; install leaves it unchanged.")
    print("Step 1/4: Building the local image (retries reuse Docker's build cache).", flush=True)
    compose("build", "bridge")
    print("Step 2/4: Guided configuration. Existing settings and keys are kept; Enter accepts saved settings.", flush=True)
    execute([sys.executable, str(ROOT / "scripts/setup.py")])
    print("Step 3/4: Checking Compose, credential access and verified TLS.", flush=True)
    compose("config", "--quiet")
    compose("run", "--rm", "--no-deps", "bridge", "validate")
    print("Step 4/4: Start the tunnel. Only one client may use this tunnel ID, including on other hosts.", flush=True)
    answer = input("Have you stopped any previous client and disabled its automatic relaunch? Type 'yes' to start: ").strip().lower()
    if answer != "yes":
        print("Not started. Configuration saved. Rerun install when ready, or use start --single-instance-confirmed after checking other clients.")
        return
    compose("up", "-d", "--no-build", "--pull", "never", "bridge")
    wait_healthy()
    print("Bridge healthy: tunnel polling and a read-only NAS probe succeeded.\n"
          "Next: enable your personal ChatGPT plugin on this tunnel and ask:\n"
          "Use the TrueNAS system_info tool to tell me the system version. Do not make any changes.\n"
          "The ChatGPT call is still required to verify the full connection.")


def reset():
    """Remove this deployment and its private local files, never read secrets."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError("Reset requires a local interactive terminal and explicit confirmation")
    if os.getuid() == 0:
        raise RuntimeError("Run reset as the non-root user who operates Compose")
    # Keep project/image selection until other deletion has succeeded, so a
    # filesystem failure can be retried against the same Compose project.
    targets = [ROOT / "config/local", ROOT / "secrets", LOCAL, ROOT / ".env"]
    for path in [ROOT / "config", *targets]:
        if path.is_symlink():
            raise RuntimeError("Reset refused: local configuration paths must not be symlinks")
    cfg = json.loads(compose("config", "--format", "json", capture=True).stdout)
    project = cfg["name"]
    selector = "label=com.docker.compose.project=" + project

    def container_ids():
        return execute(["docker", "ps", "-aq", "--filter", selector], capture=True).stdout.split()

    # Compose project names are shared across checkouts. Do not remove another
    # installation just because its project name matches this one.
    for cid in container_ids():
        labels = json.loads(execute(["docker", "inspect", "--format", "{{json .Config.Labels}}", cid], capture=True).stdout)
        if (labels.get("com.docker.compose.project.working_dir") != str(ROOT)
                or labels.get("com.docker.compose.project.config_files") != str(ROOT / "compose.yaml")):
            raise RuntimeError("Reset refused: this Compose project includes containers from another checkout. Use its original checkout or a separate project name.")
    print(f"Reset checkout: {ROOT}\nCompose project: {project}\n"
          "Will stop and remove this project's containers and non-external networks.\n"
          "Will delete .env, config/local/, secrets/ (including backups), and .local/.\n"
          "Code, Git history and Docker images are kept. Keys are not revoked; deletion is not secure erasure.", flush=True)
    if input("Type RESET to permanently remove this local deployment: ").strip() != "RESET":
        print("Reset cancelled. Nothing removed.")
        return
    try:
        compose("down", "--remove-orphans")
        networks = execute(["docker", "network", "ls", "-q", "--filter", selector], capture=True).stdout.strip()
        if container_ids() or networks:
            raise RuntimeError("Reset stopped: Docker resources remain. Local settings and credentials were kept; check Docker and retry.")
    except subprocess.CalledProcessError:
        raise RuntimeError("Reset stopped: Docker cleanup failed. Local settings and credentials were kept; check Docker and retry.") from None
    for path in targets:
        if path.is_symlink() or not path.is_dir():
            path.unlink(missing_ok=True)
        else:
            shutil.rmtree(path)
    print("Reset complete. Run python3 scripts/bridge.py install to configure again.\n"
          "If you exported COMPOSE_PROJECT_NAME or BRIDGE_IMAGE, they remain set in your shell.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "reset", "build", "validate", "start", "stop", "status", "probe", "restart", "update", "rollback"])
    parser.add_argument("--image", help="Locally built, unique candidate image tag for update")
    parser.add_argument("--single-instance-confirmed", action="store_true", help="Operator has stopped any previous host using this tunnel")
    parser.add_argument("--json", action="store_true", help="Original JSON output for status or probe")
    args = parser.parse_args()
    if args.json and args.command not in ("status", "probe"):
        parser.error("--json is only available for status and probe")
    with checkout_lock():
        cmd = args.command
        if cmd == "reset":
            reset()
            return
        LOCAL.mkdir(mode=0o700, exist_ok=True)
        if cmd == "install":
            install()
        elif cmd == "build":
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
            return show_report(cmd, json_output=args.json)
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
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error) if isinstance(error, RuntimeError) else "Operation failed; check local files and Docker status", file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print("\nInterrupted. Check Docker status before continuing. Install/reset can be retried; reset may have partially completed cleanup.", file=sys.stderr)
        sys.exit(1)
