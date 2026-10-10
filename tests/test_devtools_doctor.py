"""devtools/doctor.py says whether a machine can work on the codebase, and never changes anything."""
import hashlib
from importlib import metadata
import sqlite3

from devtools import doctor


def test_python_older_than_the_minimum_is_blocked():
    assert doctor.probe_python((3, 13, 9)).ok is False
    assert doctor.probe_python((3, 14, 0)).ok is True


def test_a_missing_package_is_named(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# pinned\nnumpy>=1.24\nnot-a-real-package==1.0\n")

    def version(name):
        if name == "not-a-real-package":
            raise metadata.PackageNotFoundError(name)
        return "1.0"

    probe = doctor.probe_packages(requirements, version)
    assert (probe.ok, probe.detail) == (False, "missing not-a-real-package")


def test_a_missing_cli_is_named():
    probe = doctor.probe_clis(lambda name: None if name == "codex" else f"/usr/bin/{name}")
    assert (probe.ok, probe.detail) == (False, "not on PATH: codex")


def test_the_databases_are_opened_read_only(tmp_path):
    folder = tmp_path / "data" / "someone"
    folder.mkdir(parents=True)
    for name in ("memory.db", "traces.db"):
        conn = sqlite3.connect(folder / name)
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    assert doctor.probe_data("someone", tmp_path).ok is True
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()} == before
    assert doctor.probe_data("nobody", tmp_path).ok is False
    assert doctor.state_root("someone", tmp_path) == tmp_path


def test_a_graph_older_than_the_last_code_commit_is_a_warning_not_a_block(tmp_path, monkeypatch, capsys):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir()
    graph.write_text("{}")
    built = int(graph.stat().st_mtime)
    stale = doctor.probe_graph(tmp_path, code_time=built + 100)
    assert (stale.ok, stale.blocking, stale.fix.split()[0:2]) == (False, False, ["graphify", "update"])
    assert doctor.probe_graph(tmp_path, code_time=built - 100).ok is True
    monkeypatch.setattr(doctor, "run", lambda ci, user: [doctor.Probe("python", True, "3.14"), stale])
    monkeypatch.delenv("CI", raising=False)
    assert doctor.main([]) == 0
    assert "warn     graph" in capsys.readouterr().out


def test_ci_mode_runs_only_what_ci_can_have():
    assert [p.id for p in doctor.run(ci=True, user="ramsay")] == ["python", "packages"]
