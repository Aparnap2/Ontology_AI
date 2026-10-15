#!/bin/sh
# Bring up the services the deterministic gate needs, and wait until each is
# actually ready. FG-1 (issue #71) cannot complete without these.
set -u

wait_for() {
  _name=$1; _cmd=$2; _tries=${3:-40}
  i=0
  while [ "$i" -lt "$_tries" ]; do
    if eval "$_cmd" >/dev/null 2>&1; then
      echo "OK   $_name"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  echo "FAIL $_name"
  return 1
}

docker start localgcp-cloudsql iterateswarm-redpanda sarthi-redis \
  ontologiai-temporal ontologiai-postgres >/dev/null 2>&1

wait_for "postgres(32768)" \
  "PGPASSWORD=iterateswarm psql -h 127.0.0.1 -p 32768 -U iterateswarm -d iterateswarm -tc 'select 1'"
wait_for "redis(6379)" \
  "python3 -c \"import socket;s=socket.create_connection(('127.0.0.1',6379),3);s.send(b'PING\r\n');import sys;sys.exit(0 if b'PONG' in s.recv(32) else 1)\""
wait_for "redpanda(9644)" \
  "curl -sf -m 3 http://127.0.0.1:9644/v1/status/ready"