"""Fetch locked upstream artifacts; never consume a user's configuration."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import urllib.request
import zipfile


def fetch(item):
    with urllib.request.urlopen(item["url"], timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise SystemExit("Upstream artifact checksum mismatch")
    return data


lock = json.loads(Path("versions.lock.json").read_text())
arch = sys.argv[1]
if arch not in ("arm64", "amd64"):
    raise SystemExit("Only Linux ARM64 and AMD64 are supported")
with zipfile.ZipFile(io.BytesIO(fetch(lock["tunnel"]["artifacts"][arch]))) as archive:
    Path("tunnel-client").write_bytes(archive.read("tunnel-client"))
    Path("legal").mkdir()
    for name in archive.namelist():
        if name in ("LICENSE", "NOTICE") or name.endswith(("-licenses.txt", ".spdx.json")):
            Path("legal", Path(name).name).write_bytes(archive.read(name))
with tarfile.open(fileobj=io.BytesIO(fetch(lock["truenas"])), mode="r:gz") as archive:
    archive.extractall("unpack", filter="data")
root, = Path("unpack").iterdir()
root.rename("source")
