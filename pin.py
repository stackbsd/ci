"""Ports commit of the newest official package build."""

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request

MIRROR = "https://pkg.FreeBSD.org"


def newest(lines):
    """Return the ports commit and timestamp of the newest build."""
    best = ("", "")
    for line in lines:
        notes = json.loads(line).get("annotations", {})
        built = notes.get("build_timestamp", "")
        commit = notes.get("ports_top_git_hash", "")
        if commit and built > best[0]:
            best = (built, commit)
    if not best[1]:
        raise ValueError("no package carries a ports commit")
    return best[1], best[0]


def packagesite(url):
    """Download a packagesite archive and yield its manifest lines."""
    with tempfile.NamedTemporaryFile(suffix=".pkg") as tmp:
        with urllib.request.urlopen(url, timeout=120) as response:
            while chunk := response.read(1 << 20):
                tmp.write(chunk)
        tmp.flush()
        done = subprocess.run(
            ("tar", "-xOf", tmp.name, "packagesite.yaml"),
            capture_output=True,
            check=True,
        )
    return done.stdout.decode().splitlines()


def main(argv=None):
    """Print the ports commit the official repo was last built from."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", required=True)
    parser.add_argument("--stream", required=True, choices=("latest", "quarterly"))
    args = parser.parse_args(argv)
    url = f"{MIRROR}/{args.abi}/{args.stream}/packagesite.pkg"
    commit, built = newest(packagesite(url))
    print(commit, built)
    return 0


if __name__ == "__main__":
    sys.exit(main())
