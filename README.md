# ci

Build and test tooling for the stackbsd ports.

## Snapshot

`snapshot.py` builds a source distfile from a commit of every driver repo in `sources.toml` and points the matching port at it.

```
python3.12 snapshot.py --ports <ports checkout> --distfiles <distfiles dir> --work <cache dir>
```

- the version is the last `v*` tag followed by the number of commits since it, so `v0.9.5` plus 54 commits is `0.9.5.54`
- `DISTVERSION` and `distinfo` of each port are rewritten in the ports checkout, which is left uncommitted
- `--ref NAME=REF` builds a branch, tag or commit of one source instead of `main`
- `--url NAME=URL` takes one source from another repo or a local checkout
- `--manifest FILE` records the commit and version of every source as JSON

Requires `git` and `uv`.

## Tests

```
python3.12 -m unittest discover -s tests -t .
```
