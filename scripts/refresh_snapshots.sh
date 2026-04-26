#!/usr/bin/env bash
# Refresh all plate snapshots. Use when visual changes are intentional.
set -e
cd "$(dirname "$0")/.."
rm -f tests/snapshots/*.sha256
.venv/bin/python -m pytest tests/test_plates_snapshot.py -v
echo "Snapshots refreshed. Review the git diff and commit."
