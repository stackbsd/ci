#!/bin/sh
# usage: build.sh <nightly|release|dev> <latest|quarterly> [snapshot options]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
JAIL=15amd64
ABI=FreeBSD:15:amd64
STATE=/var/db/stackbsd-ci
TREES=/usr/local/poudriere/ports
DISTFILES=/usr/ports/distfiles
PORTS_URL=https://github.com/stackbsd/ports
PORTS_REF=main
conf=${STACKBSD_CI_CONF:-/usr/local/etc/stackbsd-ci.conf}
if [ -r "$conf" ]; then . "$conf"; fi

channel=${1:-}
stream=${2:-}
case "$channel" in nightly|release|dev) ;; *) echo "usage: build.sh <nightly|release|dev> <latest|quarterly> [snapshot options]" >&2; exit 64 ;; esac
case "$stream" in latest|quarterly) ;; *) echo "usage: build.sh <nightly|release|dev> <latest|quarterly> [snapshot options]" >&2; exit 64 ;; esac
shift 2

mkdir -p "$STATE"
if [ "${STACKBSD_CI_LOCKED:-}" != yes ]; then
	STACKBSD_CI_LOCKED=yes exec lockf "$STATE/lock" "$0" "$channel" "$stream" "$@"
fi

name=$channel-$stream
tree_name=sb_${channel}_$stream
run=$STATE/runs/$name/$(date -u +%Y%m%dT%H%M%SZ)
overlay=$STATE/overlays/$name
mkdir -p "$run"
echo "$name started $(date -u +%FT%TZ), run $run"

# pin the tree to the commit of the official packages so they can be fetched
python3.12 "$here/pin.py" --abi "$ABI" --stream "$stream" > "$run/pin"
read -r commit built < "$run/pin"
echo "ports tree $stream at $commit, official build of $built"
tree=$TREES/$stream
if ! git -C "$tree" cat-file -e "$commit^{commit}" 2>/dev/null; then
	git -C "$tree" fetch -q --depth 1 origin "$commit"
fi
git -C "$tree" checkout -q --detach "$commit"

# start from a clean checkout of the stackbsd ports
if [ ! -d "$overlay/.git" ]; then
	git clone -q "$PORTS_URL" "$overlay"
fi
git -C "$overlay" fetch -q --prune "$PORTS_URL" "+refs/heads/*:refs/remotes/origin/*"
git -C "$overlay" checkout -q -f --detach "origin/$PORTS_REF"
git -C "$overlay" clean -q -fdx
git -C "$overlay" rev-parse HEAD > "$run/ports"

if [ "$channel" != release ]; then
	python3.12 "$here/snapshot.py" --ports "$overlay" --distfiles "$DISTFILES" \
		--work "$STATE/work" --manifest "$run/manifest.json" "$@"
fi

if ! poudriere ports -l -n -q | awk '{print $1}' | grep -qx "$tree_name"; then
	poudriere ports -c -p "$tree_name" -m null -M "$overlay"
fi

rc=0
poudriere bulk -j "$JAIL" -p "$stream" -z "$channel" -O "$tree_name" -b "$stream" \
	-f "$overlay/pkglist" || rc=$?
echo "$rc" > "$run/result"
ln -sfn "$run" "$STATE/runs/$name/last"
if [ "$rc" -ne 0 ]; then
	echo "$name failed with $rc"
	exit "$rc"
fi

if [ "$channel" != dev ]; then
	"$here/publish.sh" "$channel" "$stream"
fi
echo "$name finished $(date -u +%FT%TZ)"
