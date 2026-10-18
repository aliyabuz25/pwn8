#!/bin/sh
set -eu
exec "$(dirname "$0")/SETUP.command" "$@"
