"""The remote extract must clear stale WAL sidecars BEFORE untarring.

2026-08-23: memory.db on the Fly volume came back
`sqlite3.DatabaseError: database disk image is malformed`, which took /healthz
to 500, which made Fly's proxy stop routing, which meant the safe HTTP sync
could no longer reach the machine to replace the file.

The SFTP fallback built this command:

    cd /data && tar xzf bundle.tar.gz && rm -f bundle.tar.gz memory.db-wal ...

tar writes the fresh memory.db while the previous database's WAL is still on
disk, and SQLite replays those stale frames into the new file. The comment
above the code already said the sidecars had to go first; the code did it last.
`sync_upload.receive_sync_bundle` gets the order right, which is why the HTTP
path never produced this.
"""

import re

from orchestrator import sync


class TestExtractCommandOrder:
    def test_sidecars_are_removed_before_the_tar_runs(self):
        cmd = sync._extract_command("/data/bundle.tar.gz", "ramsay")
        rm_wal = cmd.index("memory.db-wal")
        untar = cmd.index("tar xzf")
        assert rm_wal < untar, (
            "stale WAL is removed after extraction, so it replays into the "
            f"fresh database: {cmd}"
        )

    def test_every_sidecar_for_both_databases_is_cleared(self):
        cmd = sync._extract_command("/data/bundle.tar.gz", "ramsay")
        for db in ("memory.db", "traces.db"):
            for suffix in ("-wal", "-shm"):
                assert f"{db}{suffix}" in cmd, f"{db}{suffix} not cleared"

    def test_the_bundle_is_still_removed_after_a_successful_extract(self):
        cmd = sync._extract_command("/data/bundle.tar.gz", "ramsay")
        untar = cmd.index("tar xzf")
        assert cmd.index("rm -f /data/bundle.tar.gz", untar) > untar

    def test_a_failed_extract_leaves_the_bundle_in_place_for_repair(self):
        """`rm` of the bundle must be gated on tar succeeding.

        A timed-out tar that still deleted its own source would strand the
        machine with a half-unpacked volume and nothing to re-extract from.
        """
        cmd = sync._extract_command("/data/bundle.tar.gz", "ramsay")
        tail = cmd[cmd.index("tar xzf"):]
        assert "&&" in tail, f"bundle removal is not gated on tar success: {cmd}"

    def test_the_user_id_is_confined_to_a_safe_shell_token(self):
        """The command is interpolated into a shell, so guard the one variable."""
        cmd = sync._extract_command("/data/bundle.tar.gz", "ramsay")
        assert ";" not in cmd and "|" not in cmd and "$(" not in cmd
        assert re.search(r"\bramsay/memory\.db-wal\b", cmd)


class TestCallerUsesTheHelper:
    def test_the_sftp_path_builds_its_command_through_the_helper(self):
        """Otherwise the ordering fix lives in a function nobody calls."""
        import inspect

        source = inspect.getsource(sync)
        # The old inline form must be gone.
        assert "cd /data && tar xzf" not in source, (
            "the inline extract command is still there, so the helper is dead code"
        )
        assert "_extract_command(" in source
