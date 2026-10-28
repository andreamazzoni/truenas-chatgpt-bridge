"""Strict local settings validation, shared by setup and runtime."""
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import stat


class ConfigError(Exception):
    pass


def endpoint(value):
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ConfigError("Enter a hostname or IP address, optionally with a port")
    if any(c in value for c in "/@?#\\ \t\n\r%"):
        raise ConfigError("Hostname must not contain a scheme, path, credentials or whitespace")
    port = 443
    host = value
    if value.startswith("["):
        match = re.fullmatch(r"\[([0-9a-fA-F:]+)\](?::([0-9]+))?", value)
        if not match:
            raise ConfigError("Invalid bracketed IPv6 address")
        host = match[1]
        ipaddress.IPv6Address(host)
        port = int(match[2] or 443)
    elif value.count(":") == 1:
        host, number = value.split(":")
        if not number.isascii() or not number.isdigit():
            raise ConfigError("Port must be numeric")
        port = int(number)
    elif ":" in value:
        # Pinned upstream does not reliably handle bare IPv6 plus port.
        raise ConfigError("Use [IPv6] or [IPv6]:port")
    if not 1 <= port <= 65535:
        raise ConfigError("Port must be between 1 and 65535")
    if not value.startswith("["):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if re.fullmatch(r"[0-9.]+", host):
                raise ConfigError("Invalid IPv4 address") from None
            labels = host.rstrip(".").split(".")
            if not all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", s) for s in labels):
                raise ConfigError("Invalid DNS hostname")
    return host, port


def settings(path, *, allow_legacy=False):
    cfg = json.loads(Path(path).read_text())
    legacy = {"truenas_host", "tunnel_id", "ca_file", "organization_id"}
    expected = legacy | {"truenas_api_user"}
    if not isinstance(cfg, dict) or (set(cfg) != expected and not (allow_legacy and set(cfg) == legacy)):
        raise ConfigError("Unexpected or missing settings fields; run setup")
    if "truenas_api_user" in cfg:
        api_user(cfg["truenas_api_user"])
    endpoint(cfg["truenas_host"])
    if not isinstance(cfg["tunnel_id"], str) or not re.fullmatch(r"tunnel_[a-z0-9]{32}", cfg["tunnel_id"]):
        raise ConfigError("Invalid tunnel ID")
    if cfg["ca_file"] not in ("", "truenas-ca.pem"):
        raise ConfigError("CA file must be empty or truenas-ca.pem")
    if not isinstance(cfg["organization_id"], str) or (cfg["organization_id"] and not re.fullmatch(r"org-[a-zA-Z0-9_-]{1,100}", cfg["organization_id"])):
        raise ConfigError("Invalid organization ID")
    return cfg


def api_user(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.@\\$-]{0,255}", value):
        raise ConfigError("Enter the TrueNAS user that owns the API key")
    return value


def tls_check(cfg, directory):
    ca = str(Path(directory) / cfg["ca_file"]) if cfg["ca_file"] else None
    context = ssl.create_default_context(cafile=ca)
    host, port = endpoint(cfg["truenas_host"])
    # TLS handshake only: no HTTP, no API key, no redirects or certificate TOFU.
    with socket.create_connection((host, port), timeout=8) as raw:
        with context.wrap_socket(raw, server_hostname=host):
            pass


def secret(path, *, read=True):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ConfigError("Required credential file is missing or is a symlink")
    mode = path.stat()
    if mode.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError("Credential file must have mode 0600 or 0400")
    if not 1 <= mode.st_size <= 4096:
        raise ConfigError("Credential file has an invalid size")
    if not read:
        with path.open("rb"):
            pass  # Validate access as the current container/host user.
        return None
    value = path.read_text().rstrip("\n")
    if not value or not value.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in value):
        raise ConfigError("Credential must be a single printable ASCII token")
    return value
