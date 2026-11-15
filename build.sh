#!/bin/sh
# usage: build.sh <nightly|release|dev> <latest|quarterly> [snapshot options]
set -eu

JAIL=15amd64
ABI=FreeBSD:15:amd64
STATE=/var/db/stackbsd-ci
TREES=/usr/local/poudriere/ports
DISTFILES=/usr/ports/distfiles
PORTS_URL=https://github.com/stackbsd/ports
PORTS_REF=main

here=$(cd "$(dirname "$0")" && pwd)
conf=${STACKBSD_CI_CONF:-/usr/local/etc/stackbsd-ci.conf}
if [ -r "$conf" ]; then
	. "$conf"
fi

usage() {
	echo "usage: build.sh <nightly|release|dev> <latest|quarterly>" \
		"[snapshot options]" >&2
	exit 64
}

pin_tree() {
	python3.12 "$here/pin.py" --abi "$ABI" --stream "$stream" > "$run/pin"
	read -r commit built < "$run/pin"
	echo "ports tree $stream at $commit, official build of $built"

	if ! git -C "$tree" cat-file -e "$commit^{commit}" 2>/dev/null; then
		git -C "$tree" fetch -q --depth 1 origin "$commit"
	fi
	git -C "$tree" checkout -q --detach "$commit"
}

checkout_overlay() {
	if [ ! -d "$overlay/.git" ]; then
		git clone -q "$PORTS_URL" "$overlay"
	fi
	git -C "$overlay" fetch -q --prune "$PORTS_URL" \
		"+refs/heads/*:refs/remotes/origin/*"
	git -C "$overlay" checkout -q -f --detach "origin/$PORTS_REF"
	git -C "$overlay" clean -q -fdx
	git -C "$overlay" rev-parse HEAD > "$run/ports"

	if ! poudriere ports -l -n -q | awk '{print $1}' | grep -qx "$tree_name"; then
		poudriere ports -c -p "$tree_name" -m null -M "$overlay"
	fi
}

read_series() {
	series=$(awk '$1 == "DISTVERSION=" {split($2, v, "."); print v[1] "." v[2]}' \
		"$overlay/net/openstack-runtime/Makefile.distfiles")
	case "$series" in
	[0-9]*.[0-9]*) ;;
	*)
		echo "no openstack series in the runtime port" >&2
		exit 1
		;;
	esac
	echo "$series" > "$run/series"
}

snapshot_drivers() {
	python3.12 "$here/snapshot.py" \
		--ports "$overlay" \
		--distfiles "$DISTFILES" \
		--work "$STATE/work" \
		--manifest "$run/manifest.json" \
		"$@"
}

build_packages() {
	set_name=$(echo "$series" | tr . _)_$channel
	rc=0
	poudriere bulk \
		-j "$JAIL" \
		-p "$stream" \
		-z "$set_name" \
		-O "$tree_name" \
		-b "$stream" \
		-f "$overlay/pkglist" || rc=$?

	echo "$rc" > "$run/result"
	ln -sfn "$run" "$STATE/runs/$name/last"
	if [ "$rc" -ne 0 ]; then
		echo "$name failed with $rc"
		exit "$rc"
	fi
}

channel=${1:-}
stream=${2:-}
case "$channel" in nightly | release | dev) ;; *) usage ;; esac
case "$stream" in latest | quarterly) ;; *) usage ;; esac
shift 2

# one build at a time
mkdir -p "$STATE"
if [ "${STACKBSD_CI_LOCKED:-}" != yes ]; then
	STACKBSD_CI_LOCKED=yes exec lockf "$STATE/lock" "$0" "$channel" "$stream" "$@"
fi

name=$channel-$stream
tree=$TREES/$stream
tree_name=sb_${channel}_$stream
overlay=$STATE/overlays/$name
run=$STATE/runs/$name/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$run"

echo "$name started $(date -u +%FT%TZ), run $run"

# pin the tree to the commit of the official packages so they can be fetched
pin_tree
checkout_overlay
read_series
if [ "$channel" != release ]; then
	snapshot_drivers "$@"
fi
build_packages
if [ "$channel" != dev ]; then
	"$here/publish.sh" "$series" "$channel" "$stream"
fi

echo "$name finished $(date -u +%FT%TZ)"
