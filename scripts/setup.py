#!/usr/bin/env python3
"""Interactive, repeatable setup. Run locally in a terminal, never paste keys."""
import argparse
import getpass
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
from config import ConfigError, secret, settings, tls_check  # noqa: E402


def private_write(path, data):
    if path.is_symlink():
        raise ConfigError("Refusing to overwrite a symlink")
    fd, name = tempfile.mkstemp(prefix=".setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def prompt(label, old=""):
    value = input(f"{label}" + (f" [{old}]" if old else "") + ": ").strip()
    return value or old


def validate():
    directory = ROOT / "config/local"
    cfg = settings(directory / "settings.json")
    for name in ("openai_api_key", "truenas_api_key"):
        secret(ROOT / "secrets" / name, read=False)
    tls_check(cfg, directory)
    print("Local files, permissions, hostname and verified TLS: OK (no authentication performed)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        validate()
        return
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ConfigError("Setup requires a local interactive terminal with hidden input")
    if os.getuid() == 0:
        raise ConfigError("Run setup as the non-root user who will operate Compose")
    os.umask(0o077)
    directory = ROOT / "config/local"
    credentials = ROOT / "secrets"
    for folder in (directory, credentials):
        if folder.is_symlink():
            raise ConfigError("Configuration directories must not be symlinks")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
    path = directory / "settings.json"
    old = settings(path) if path.exists() else {}
    print("Reuse the existing tunnel and keys. Secrets are entered here with echo disabled.")
    cfg = {"truenas_host": prompt("TrueNAS hostname or IP (no scheme/path; optional :port)", old.get("truenas_host", "")),
           "tunnel_id": prompt("Existing OpenAI tunnel ID", old.get("tunnel_id", "")),
           "organization_id": prompt("Platform organization ID (optional)", old.get("organization_id", "")),
           "ca_file": old.get("ca_file", "")}
    cert = prompt("Path to independently verified PEM CA/certificate (blank keeps current/system trust)")
    if cert:
        source = Path(cert).expanduser()
        ssl.create_default_context(cafile=str(source))
        private_write(directory / "truenas-ca.pem", source.read_text())
        cfg["ca_file"] = "truenas-ca.pem"
    # Validate configuration and TLS before asking for a credential.
    fd, check_name = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(cfg, stream)
        settings(check_name)
        tls_check(cfg, directory)
    finally:
        os.unlink(check_name)
    for name, label in (("openai_api_key", "Existing OpenAI runtime key"), ("truenas_api_key", "Existing TrueNAS API key")):
        target = credentials / name
        if target.exists():
            secret(target, read=False)
            print(f"Keeping existing {name}; no secret displayed.")
            continue
        value = getpass.getpass(label + " (hidden): ")
        if not value or len(value) > 4096 or not value.isascii() or any(not 33 <= ord(c) <= 126 for c in value):
            raise ConfigError("Invalid credential token; value not displayed")
        private_write(target, value + "\n")
    private_write(path, json.dumps(cfg, indent=2) + "\n")
    env = ROOT / ".env"
    if not env.exists():
        private_write(env, f"BRIDGE_UID={os.getuid()}\nBRIDGE_GID={os.getgid()}\n")
    validate()
    print("Setup saved. No tunnel started. Stop the previous stdio instance before starting this bridge.")


if __name__ == "__main__":
    try:
        main()
    except (ConfigError, ValueError, OSError, ssl.SSLError, EOFError, KeyboardInterrupt):
        print("Setup failed; check the hostname, tunnel ID, PEM certificate, file access and TLS. No secret displayed.", file=sys.stderr)
        sys.exit(1)
