# memory/db.py

> memory.db connection management, schema initialization. 37 tables.

## What It Does

Opens SQLite connection with WAL mode, initializes all 37 tables if they don't exist. Provides connection context manager.

## Schema

See [[data/memory-db]] for full table listing.

## Called By

[[orchestrator/runner]] (init), all memory modules.

## Last Modified By Harness

Never — created 2026-04-01.
