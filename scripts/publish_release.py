"""Idempotently preserve 1.2.0 and publish the checked 1.2.1 GitHub release.

Only invoked by the repository's guarded Actions jobs. A rollback version is
prepared separately and is never automatically published as a newer release.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

BASELINE = "59b8ee3aae43a28be15a12a5d813d4975a3d7c42"
REPO = "lenni76/SolarFlow2400ProAPI"
MANIFEST = "custom_components/solarflow2400_api/manifest.json"


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def ensure_release(tag, commit, notes, title, *, latest):
    exists = subprocess.run(
        ["gh", "release", "view", tag, "--repo", REPO], capture_output=True
    )
    if exists.returncode == 0:
        subprocess.run(["git", "fetch", "origin", f"refs/tags/{tag}"], check=True)
        if output("git", "rev-parse", "FETCH_HEAD^{commit}") != commit:
            raise RuntimeError(
                f"Existing {tag} points to another commit; refusing to move it"
            )
        print(f"Verified existing release {tag} at {commit}")
        return
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            REPO,
            "--target",
            commit,
            "--title",
            title,
            "--notes-file",
            str(notes),
            f"--latest={str(latest).lower()}",
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REPOSITORY") != REPO
    ):
        raise RuntimeError(
            "Release publication is restricted to this repository's Actions jobs"
        )
    baseline_manifest = json.loads(output("git", "show", f"{BASELINE}:{MANIFEST}"))
    if baseline_manifest["version"] != "1.2.0":
        raise RuntimeError("Baseline does not contain the expected original version")
    ensure_release(
        "v1.2.0",
        BASELINE,
        Path("docs/RELEASE-1.2.0.md"),
        "1.2.0 – unveränderter bisheriger Stand",
        latest=False,
    )
    if args.baseline_only:
        return
    commit = output("git", "rev-parse", "HEAD")
    if commit != os.environ["GITHUB_SHA"]:
        raise RuntimeError("Checkout differs from the checked commit")
    if json.loads(Path(MANIFEST).read_text())["version"] != "1.2.1":
        raise RuntimeError("This release job is restricted to version 1.2.1")
    ensure_release(
        "v1.2.1",
        commit,
        Path("RELEASE_NOTES-1.2.1.md"),
        "1.2.1 – API-Korrekturen und robustere HA-Steuerung",
        latest=True,
    )


if __name__ == "__main__":
    main()
