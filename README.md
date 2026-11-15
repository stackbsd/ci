# ci

Build and test tooling required by the stackbsd ports.

- `snapshot.py` builds a source distfile for each repo in `sources.toml` so they can be built without releasing to pypi
- `build.sh` builds every port with poudriere and publishes the result
- `publish.sh` called by build script to publish the result to the repo host using rsync
- `nightly.sh` is the cron job to run both the nightly and release builds
- `.github/workflows/unit.yml` is the reusable workflow the driver repos call to run ruff and their unit tests

Settings are read from `/usr/local/etc/stackbsd-ci.conf`:

```
SIGNING_KEY=/path/to/signing.key
PUBLISH=publishuser@repo-host:/var/db/pkgrepo
```

## Published layout

```
/2026.1/${ABI}/latest             released versions on the latest branch
/2026.1/${ABI}/quarterly          released versions on the quarterly branch
/2026.1/${ABI}/nightly/latest     drivers from main on the latest branch
/2026.1/${ABI}/nightly/quarterly  drivers from main on the quarterly branch
```
