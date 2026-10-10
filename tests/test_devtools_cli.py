"""bin/mpdev (devtools/cli.py) is one command in front of every developer tool."""
import importlib
import inspect
from pathlib import Path
import subprocess
import sys
import types

from devtools import cli

ROOT = Path(__file__).resolve().parent.parent


def test_help_lists_every_command(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: mpdev <command> [args]")
    assert all(f"  {name}" in out for name in cli.COMMANDS)


def test_an_unknown_command_exits_2(capsys):
    assert cli.main(["nope"]) == 2
    assert "no command 'nope'" in capsys.readouterr().err


def test_every_command_has_a_main_that_takes_its_arguments():
    for name, (module, _) in cli.COMMANDS.items():
        main = importlib.import_module(module).main
        assert list(inspect.signature(main).parameters) == ["argv"], name


def test_a_command_gets_the_rest_of_the_arguments(monkeypatch):
    seen = []
    monkeypatch.setitem(sys.modules, "devtools.fake", types.SimpleNamespace(main=lambda argv: seen.append(argv) or 0))
    monkeypatch.setitem(cli.COMMANDS, "fake", ("devtools.fake", "a test command"))
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    assert cli.main(["fake", "--day", "2026-10-10"]) == 0
    assert seen == [["--day", "2026-10-10"]] and sys.argv[0] == "mpdev fake"


def test_the_launcher_runs_mpdev():
    done = subprocess.run([str(ROOT / "bin" / "mpdev"), "help"], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.startswith("usage: mpdev")
