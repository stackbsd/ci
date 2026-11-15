"""Snapshot of the driver repos as distfiles for a ports checkout."""

import argparse
import dataclasses
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib

DESCRIBE = re.compile(r"^v(?P<tag>\d+(\.\d+)*)-(?P<ahead>\d+)-g[0-9a-f]+$")
DISTVERSION = re.compile(r"^DISTVERSION=.*$", re.MULTILINE)
PORTREVISION = re.compile(r"^PORTREVISION=.*\n", re.MULTILINE)


class SnapshotError(Exception):
    """Failure to take a snapshot."""


@dataclasses.dataclass(frozen=True)
class Source:
    """Driver repo and the port built from it."""

    name: str
    url: str
    port: str
    ref: str = "main"


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """Distfile built from one commit of a source."""

    name: str
    port: str
    commit: str
    timestamp: int
    version: str
    distfile: str
    sha256: str
    size: int


def git(*args, cwd=None):
    """Run git and return its output."""
    done = subprocess.run(
        ("git", *args), cwd=cwd, capture_output=True, text=True, check=False
    )
    if done.returncode:
        raise SnapshotError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def load_sources(path, urls, refs):
    """Read the sources file and apply the overrides."""
    with open(path, "rb") as f:
        table = tomllib.load(f)
    unknown = sorted((set(urls) | set(refs)) - set(table))
    if unknown:
        raise SnapshotError(f"no source named {', '.join(unknown)} in {path}")
    return [
        Source(
            name=name,
            url=urls.get(name, entry["url"]),
            port=entry["port"],
            ref=refs.get(name, "main"),
        )
        for name, entry in table.items()
    ]


def version_from(describe):
    """Turn git describe output into a snapshot version."""
    match = DESCRIBE.match(describe)
    if not match:
        raise SnapshotError(f"cannot derive a version from {describe}")
    if match["ahead"] == "0":
        return match["tag"]
    return f"{match['tag']}.{match['ahead']}"


def mirror(source, work):
    """Fetch the source into its mirror and return the mirror path."""
    path = work / "mirrors" / f"{source.name}.git"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        git("init", "--bare", "-q", str(path))
    git(
        "fetch", "-q", "--prune", "--force", "--tags", source.url,
        "+refs/heads/*:refs/heads/*",
        cwd=path,
    )  # fmt: skip
    return path


def build_sdist(repo, commit, version, distfiles):
    """Build the sdist of a commit and return its path."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = pathlib.Path(tmp) / "tree"
        out = pathlib.Path(tmp) / "out"
        tree.mkdir()
        archive = subprocess.run(
            ("git", "archive", commit), cwd=repo, capture_output=True, check=False
        )
        if archive.returncode:
            raise SnapshotError(f"git archive {commit} failed")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tree, filter="data")
        for cmd in (
            ("uv", "version", "--frozen", version),
            ("uv", "build", "--sdist", "-o", str(out)),
        ):
            done = subprocess.run(
                cmd, cwd=tree, capture_output=True, text=True, check=False
            )
            if done.returncode:
                raise SnapshotError(f"{' '.join(cmd)} failed: {done.stderr.strip()}")
        built = list(out.glob("*.tar.gz"))
        if len(built) != 1:
            raise SnapshotError(f"expected one sdist and found {len(built)}")
        distfiles.mkdir(parents=True, exist_ok=True)
        target = distfiles / built[0].name
        target.write_bytes(built[0].read_bytes())
        return target


def take(source, work, distfiles):
    """Build the distfile of a source at its ref."""
    repo = mirror(source, work)
    commit = git("rev-parse", "--verify", f"{source.ref}^{{commit}}", cwd=repo)
    describe = git("describe", "--tags", "--long", "--match", "v*", commit, cwd=repo)
    version = version_from(describe)
    sdist = build_sdist(repo, commit, version, distfiles)
    data = sdist.read_bytes()
    return Snapshot(
        name=source.name,
        port=source.port,
        commit=commit,
        timestamp=int(git("show", "-s", "--format=%ct", commit, cwd=repo)),
        version=version,
        distfile=sdist.name,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def stamp_makefile(text, version):
    """Return the port Makefile with the snapshot version."""
    text, count = DISTVERSION.subn(f"DISTVERSION=\t{version}", text)
    if count != 1:
        raise SnapshotError(f"expected one DISTVERSION line and found {count}")
    return PORTREVISION.sub("", text)


def distinfo(snap):
    """Return the distinfo of a snapshot."""
    return (
        f"TIMESTAMP = {snap.timestamp}\n"
        f"SHA256 ({snap.distfile}) = {snap.sha256}\n"
        f"SIZE ({snap.distfile}) = {snap.size}\n"
    )


def stamp_port(ports, snap):
    """Point the port at the snapshot distfile."""
    port = ports / snap.port
    makefile = port / "Makefile"
    if not makefile.exists():
        raise SnapshotError(f"no port at {port}")
    makefile.write_text(stamp_makefile(makefile.read_text(), snap.version))
    (port / "distinfo").write_text(distinfo(snap))


def pairs(values):
    """Parse NAME=VALUE options into a dict."""
    out = {}
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep or not name or not rest:
            raise SnapshotError(f"expected NAME=VALUE and got {value}")
        out[name] = rest
    return out


def main(argv=None):
    """Snapshot every source into the distfiles and ports directories."""
    here = pathlib.Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", type=pathlib.Path, required=True)
    parser.add_argument("--distfiles", type=pathlib.Path, required=True)
    parser.add_argument("--work", type=pathlib.Path, required=True)
    parser.add_argument("--sources", type=pathlib.Path, default=here / "sources.toml")
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--url", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--ref", action="append", default=[], metavar="NAME=REF")
    args = parser.parse_args(argv)
    try:
        sources = load_sources(args.sources, pairs(args.url), pairs(args.ref))
        snaps = []
        for source in sources:
            snap = take(source, args.work, args.distfiles)
            stamp_port(args.ports, snap)
            snaps.append(snap)
            print(f"{snap.name} {snap.version} {snap.commit[:12]} ({source.ref})")
    except SnapshotError as err:
        print(f"snapshot: {err}", file=sys.stderr)
        return 1
    if args.manifest:
        args.manifest.write_text(
            json.dumps([dataclasses.asdict(s) for s in snaps], indent=2) + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
