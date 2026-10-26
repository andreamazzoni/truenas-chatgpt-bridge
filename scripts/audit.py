#!/usr/bin/env python3
"""Audit tracked paths and image layers without reading real credential files.

--build-check creates disposable non-secret canaries in ignored directories,
rebuilds the local image and verifies that no canary entered any image layer.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="truenas-chatgpt-bridge:0.1.0")
    parser.add_argument("--build-check", action="store_true")
    args = parser.parse_args()
    paths = run(["git", "ls-files", "-z"], stdout=subprocess.PIPE).stdout.decode().split("\0")
    for path in filter(None, paths):
        if path == ".env" or path.startswith(("secrets/", "config/local/", ".local/")):
            raise RuntimeError("Private file is tracked: " + path)
        data = (ROOT / path).read_bytes()
        private_key_header = b"-----BEGIN " + b"PRIVATE KEY-----"
        if re.search(rb"sk-[A-Za-z0-9_-]{20,}", data) or private_key_header in data:
            raise RuntimeError("Possible credential found in tracked file: " + path)
    lock = json.loads((ROOT / "versions.lock.json").read_text())
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert all(image in dockerfile for image in lock["images"].values()), "Base image pins differ from lock"
    print("PASS: tracked paths, credential-pattern scan and base image pins")
    canary = "BRIDGE_BUILD_EXCLUSION_CANARY_" + uuid.uuid4().hex
    created = []
    try:
        if args.build_check:
            for folder in ("secrets", "config/local", ".local"):
                directory = ROOT / folder
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = directory / ("audit-canary-" + uuid.uuid4().hex)
                path.write_text(canary)
                created.append(path)
            run(["docker", "buildx", "build", "--load", "-t", args.image, "."])
        config = json.loads(run(["docker", "image", "inspect", args.image], stdout=subprocess.PIPE).stdout)[0]["Config"]
        assert config["User"] not in ("", "0", "root", "0:0")
        assert not any(value.startswith(("TRUENAS_API_KEY=", "OPENAI_API_KEY=", "CONTROL_PLANE_API_KEY=")) for value in config["Env"])
        with tempfile.TemporaryDirectory(prefix="bridge-image-audit-") as tmp:
            archive_path = Path(tmp) / "image.tar"
            run(["docker", "image", "save", "-o", str(archive_path), args.image])
            with tarfile.open(archive_path) as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    stream = archive.extractfile(member)
                    head = stream.read(2)
                    stream.seek(0)
                    reader = gzip.GzipFile(fileobj=stream) if head == b"\x1f\x8b" else stream
                    tail = b""
                    while chunk := reader.read(1024 * 1024):
                        data = tail + chunk
                        if canary.encode() in data:
                            raise RuntimeError("Ignored canary entered an image layer")
                        tail = data[-len(canary):]
        print("PASS: image runs non-root, no credential environment baked in, no ignored canary in any layer")
    finally:
        for path in created:
            path.unlink()


if __name__ == "__main__":
    main()
