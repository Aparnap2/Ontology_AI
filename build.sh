#!/usr/bin/env bash
# Build the Go core binaries that the deploy artifacts start.
#
# These are the ONLY real entrypoints: apps/core/cmd/{server,worker,consumer}.
# The previous build script targeted ./apps/core/cmd/demo/main.go, which does
# not exist in the repository, so every deploy path that used it failed at the
# build step.
set -euo pipefail

cd "$(dirname "$0")/apps/core"
mkdir -p ../../bin

echo "Building server..."
go build -o ../../bin/server ./cmd/server
echo "Building worker..."
go build -o ../../bin/worker ./cmd/worker
echo "Building consumer..."
go build -o ../../bin/consumer ./cmd/consumer

echo "Binaries in ./bin:"
ls -1 ../../bin
