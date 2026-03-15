#!/bin/bash
# Wrapper for launchd — /bin/bash has Full Disk Access, python3 may not.
# This ensures Messages.db is readable for iMessage approval gates.
cd /Users/taylerramsay/Projects/mindpattern-v3
exec /opt/homebrew/bin/python3 run.py "$@"
