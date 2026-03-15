#!/bin/bash
# Wrapper for launchd — /bin/bash has Full Disk Access.
cd /Users/taylerramsay/Projects/mindpattern-v3
exec /opt/homebrew/bin/python3 autoresearch.py "$@"
