"""Build a higher-version rollback from the immutable original commit, offline."""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

BASELINE = "59b8ee3aae43a28be15a12a5d813d4975a3d7c42"
MANIFEST = "custom_components/solarflow2400_api/manifest.json"


def original(path):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"])


def build(version, destination):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use a plain semantic version")
    if tuple(map(int, version.split("."))) <= (1, 2, 1):
        raise ValueError("Rollback version must be newer than 1.2.1")
    paths = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            BASELINE,
            "custom_components/solarflow2400_api",
            "hacs.json",
        ],
        text=True,
    ).splitlines()
    files = {path: original(path) for path in paths if "__pycache__" not in path}
    baseline_hashes = {
        path: hashlib.sha256(data).hexdigest()
        for path, data in files.items()
        if path.endswith(".py")
    }
    manifest = json.loads(files[MANIFEST])
    if manifest["version"] != "1.2.0":
        raise ValueError("Unexpected original version")
    manifest["version"] = version
    files[MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"SolarFlow2400-API-{version}-Rollback.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path, data in sorted(files.items()):
            output.writestr(path, data)
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        for path, expected in baseline_hashes.items():
            assert hashlib.sha256(check.read(path)).hexdigest() == expected
    record = {
        "version": version,
        "baseline_version": "1.2.0",
        "baseline_commit": BASELINE,
        "runtime_python_unchanged": True,
        "python_sha256": baseline_hashes,
        "only_manifest_field_changed": "version",
        "published": False,
        "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    archive.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.2.2")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    options = parser.parse_args()
    print(build(options.version, options.output))
