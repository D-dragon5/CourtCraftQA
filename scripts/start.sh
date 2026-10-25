#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
exec python3 token_viewer.py --config config.json
