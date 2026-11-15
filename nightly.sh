#!/bin/sh
# usage: nightly.sh
set -u

here=$(cd "$(dirname "$0")" && pwd)
LOGDIR=/var/log/stackbsd-ci
conf=${STACKBSD_CI_CONF:-/usr/local/etc/stackbsd-ci.conf}
if [ -r "$conf" ]; then . "$conf"; fi

mkdir -p "$LOGDIR"
stamp=$(date -u +%Y%m%d)
failed=0
for stream in latest quarterly; do
	for channel in nightly release; do
		log=$LOGDIR/$stamp-$channel-$stream.log
		if ! "$here/build.sh" "$channel" "$stream" > "$log" 2>&1; then
			echo "$channel-$stream failed, see $log"
			failed=1
		fi
	done
done
find "$LOGDIR" -name '*.log' -mtime +30 -delete
exit "$failed"
