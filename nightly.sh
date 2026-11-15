#!/bin/sh
# usage: nightly.sh
set -u

LOGDIR=/var/log/stackbsd-ci
KEEP_DAYS=30

here=$(cd "$(dirname "$0")" && pwd)
conf=${STACKBSD_CI_CONF:-/usr/local/etc/stackbsd-ci.conf}
if [ -r "$conf" ]; then
	. "$conf"
fi

mkdir -p "$LOGDIR"
stamp=$(date -u +%Y%m%d)
failed=0

for stream in latest quarterly; do
	for channel in nightly release; do
		log=$LOGDIR/$stamp-$channel-$stream.log
		if "$here/build.sh" "$channel" "$stream" > "$log" 2>&1; then
			continue
		fi
		echo "$channel-$stream failed, see $log"
		failed=1
	done
done

find "$LOGDIR" -name '*.log' -mtime "+$KEEP_DAYS" -delete
exit "$failed"
