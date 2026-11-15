#!/bin/sh
# usage: publish.sh <channel> <latest|quarterly>
set -eu

JAIL=15amd64
ABI=FreeBSD:15:amd64
STATE=/var/db/stackbsd-ci
PACKAGES=/usr/local/poudriere/data/packages
LOGS=/usr/local/poudriere/data/logs/bulk
KEEP=7
SIGNING_KEY=
PUBLISH=
conf=${STACKBSD_CI_CONF:-/usr/local/etc/stackbsd-ci.conf}
if [ -r "$conf" ]; then . "$conf"; fi

channel=$1
stream=$2
name=$channel-$stream
overlay=$STATE/overlays/$name
built=$PACKAGES/$JAIL-$stream-$channel
site=$STATE/site/$ABI
stamp=$(date -u +%Y%m%dT%H%M%SZ)
stage=$site/$name.d/$stamp

# only packages of our own ports are published
mkdir -p "$stage/All"
for pkg in "$built"/All/*.pkg; do
	origin=$(pkg query -F "$pkg" %o)
	if [ -d "$overlay/$origin" ]; then
		cp "$pkg" "$stage/All/"
	fi
done
count=$(find "$stage/All" -name '*.pkg' | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
	echo "no packages of our own ports in $built" >&2
	exit 1
fi

# a dependency built here is missing from the official repo at this version
log=$LOGS/$JAIL-$stream-$channel/latest/.poudriere.ports.built
if [ -r "$log" ]; then
	awk '{print $1}' "$log" | sed 's/@.*//' | sort -u | while read -r origin; do
		# poudriere always builds pkg itself
		if [ "$origin" != ports-mgmt/pkg ] && [ ! -d "$overlay/$origin" ]; then
			echo "warning: $origin was built locally and is not published"
		fi
	done
fi

if [ -n "$SIGNING_KEY" ]; then
	pkg repo -q "$stage" "$SIGNING_KEY"
else
	pkg repo -q "$stage"
fi
ln -sfn "$name.d/$stamp" "$site/$name"

# drop all but the newest copies
ls -1 "$site/$name.d" | sort -r | tail -n "+$((KEEP + 1))" | while read -r old; do
	rm -rf "$site/$name.d/${old:?}"
done

echo "$name staged $count packages in $stage"
if [ -z "$PUBLISH" ]; then
	exit 0
fi
# packages must land before the link that makes them current
rsync -a --mkpath "$stage/" "$PUBLISH/$ABI/$name.d/$stamp/"
rsync -a "$site/$name" "$PUBLISH/$ABI/"
rsync -a --delete "$site/$name.d/" "$PUBLISH/$ABI/$name.d/"
echo "$name published to $PUBLISH/$ABI/$name"
