# ci

Build and test tooling for the stackbsd ports.

## Snapshot

`snapshot.py` builds a source distfile from a commit of every driver repo in `sources.toml` and points the matching port at it.

```
python3.12 snapshot.py --ports <ports checkout> --distfiles <distfiles dir> --work <cache dir>
```

- the version is the last `v*` tag followed by the number of commits since it, so `v0.9.5` plus 54 commits is `0.9.5.54`
- `DISTVERSION` and `distinfo` of each port are rewritten in the ports checkout, which is left uncommitted
- distfiles go in a `stackbsd-snapshot` subdirectory of the distfiles directory, apart from release tarballs of the same name
- `--ref NAME=REF` builds a branch, tag or commit of one source instead of `main`
- `--url NAME=URL` takes one source from another repo or a local checkout
- `--manifest FILE` records the commit and version of every source as JSON

Requires `git` and `uv`.

## Package builds

`build.sh <nightly|release|dev> <latest|quarterly> [snapshot options]` builds every port in `pkglist` of stackbsd/ports with poudriere and publishes the result.

- `nightly` builds the drivers from a snapshot of `main`, `release` builds the versions the ports name, `dev` builds like `nightly` and is not published
- `latest` and `quarterly` select the FreeBSD ports branch
- `pin.py` finds the ports commit the official packages were last built from and the tree is checked out there, so dependencies are fetched from the official repo instead of built
- snapshot options are passed to `snapshot.py`, for example `build.sh dev latest --ref nova-bhyve=my-branch`
- `PORTS_REF=my-branch build.sh dev latest` builds a branch of stackbsd/ports
- `publish.sh` signs a repo of our own packages only and uploads it to `<ABI>/<channel>-<stream>` behind a link that moves once the upload is complete
- `nightly.sh` runs the nightly and release builds of both branches

Settings are read from `/usr/local/etc/stackbsd-ci.conf`:

```
SIGNING_KEY=/usr/local/etc/ssl/keys/stackbsd-pkg.key
PUBLISH=pkgsync@repo:/var/db/pkgrepo
```

Requires `poudriere` with a `15amd64` jail and `latest` and `quarterly` ports trees, `rsync`, `git` and `uv`.

### Using the packages

```
stackbsd: {
  url: "https://pkg.stackbsd.org/${ABI}/release-latest",
  signature_type: "pubkey",
  pubkey: "/usr/local/etc/ssl/certs/stackbsd-pkg.pub",
  enabled: yes
}
```

The public key is at https://pkg.stackbsd.org/stackbsd-pkg.pub. Use the channel that matches the branch of the FreeBSD repo on the machine.

## Tests

```
python3.12 -m unittest discover -s tests -t .
```
