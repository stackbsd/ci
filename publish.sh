#!/bin/sh
# usage: publish.sh <series> <nightly|release> <latest|quarterly>
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
if [ -r "$conf" ]; then
	. "$conf"
fi

stage_packages() {
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
}

warn_local_builds() {
	log=$LOGS/$JAIL-$stream-$set_name/latest/.poudriere.ports.built
	if [ ! -r "$log" ]; then
		return
	fi
	awk '{print $1}' "$log" | sed 's/@.*//' | sort -u | while read -r origin; do
		# poudriere always builds pkg itself
		if [ "$origin" = ports-mgmt/pkg ] || [ -d "$overlay/$origin" ]; then
			continue
		fi
		echo "warning: $origin was built locally and is not published"
	done
}

sign_repo() {
	if [ -n "$SIGNING_KEY" ]; then
		pkg repo -q "$stage" "$SIGNING_KEY"
	else
		pkg repo -q "$stage"
	fi
}

make_current() {
	mkdir -p "$(dirname "$site/$link")"
	ln -sfn "$target" "$site/$link"

	ls -1 "$site/$store" | sort -r | tail -n "+$((KEEP + 1))" |
		while read -r old; do
			rm -rf "$site/$store/${old:?}"
		done
}

upload() {
	remote=$PUBLISH/$series/$ABI
	# packages must land before the link that makes them current
	rsync -a --mkpath "$stage/" "$remote/$store/$stamp/"
	# the link is copied into its parent so an existing one is replaced
	rsync -a --mkpath "$site/$link" "$remote/$(dirname "$link")/"
	rsync -a --delete "$site/$store/" "$remote/$store/"
	echo "$name published to $remote/$link"
}

series=$1
channel=$2
stream=$3

name=$channel-$stream
set_name=$(echo "$series" | tr . _)_$channel
overlay=$STATE/overlays/$name
built=$PACKAGES/$JAIL-$stream-$set_name

site=$STATE/site/$series/$ABI
stamp=$(date -u +%Y%m%dT%H%M%SZ)
store=.store/$name
stage=$site/$store/$stamp

# released packages sit at the top and nightly ones a level down
case "$channel" in
release)
	link=$stream
	target=$store/$stamp
	;;
*)
	link=$channel/$stream
	target=../$store/$stamp
	;;
esac

# only packages of our own ports are published
stage_packages
warn_local_builds
sign_repo
make_current
echo "$name staged $count packages in $stage"

if [ -n "$PUBLISH" ]; then
	upload
fi
