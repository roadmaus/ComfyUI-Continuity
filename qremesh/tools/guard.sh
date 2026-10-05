#!/bin/sh
# guard.sh SECONDS MB cmd... : run cmd, kill it past SECONDS or past MB resident memory.
lim_s=$1; lim_mb=$2; shift 2
"$@" &
pid=$!
t=0
while kill -0 $pid 2>/dev/null; do
  rss=$(ps -o rss= -p $pid 2>/dev/null | tr -d ' ')
  if [ -n "$rss" ] && [ "$rss" -gt $((lim_mb * 1024)) ]; then kill -9 $pid; echo "GUARD: killed at ${rss}KB after ${t}s" >&2; exit 137; fi
  if [ $t -ge $((lim_s * 4)) ]; then kill -9 $pid; echo "GUARD: killed after ${lim_s}s" >&2; exit 137; fi
  sleep 0.25; t=$((t + 1))
done
wait $pid
