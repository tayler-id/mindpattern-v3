"""tools/bakeoff.py hides which version is which until --reveal."""
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("bakeoff", ROOT / "tools" / "bakeoff.py")
bakeoff = importlib.util.module_from_spec(SPEC)
sys.modules["bakeoff"] = bakeoff
SPEC.loader.exec_module(bakeoff)


def test_the_page_hides_the_sources_and_the_key_reveals_them(tmp_path, capsys):
    a, b = tmp_path / "opus5.md", tmp_path / "opus55.md"
    a.write_text("# Issue\n\nThis matters a lot.\n")
    b.write_text("# Issue\n\nTeams lose the export on November 1.\n")
    key = bakeoff.build(a, b, tmp_path / "out", rng=random.Random(1))
    page = (tmp_path / "out" / "compare.html").read_text()
    assert "opus5" not in page and "opus55" not in page
    assert "Version 1" in page and "Version 2" in page
    assert "1 writing-policy violations" in page and "0 writing-policy violations" in page
    assert json.loads((tmp_path / "out" / "answer-key.json").read_text()) == key
    assert {entry["side"] for entry in key.values()} == {"a", "b"}

    assert bakeoff.main(["--reveal", str(tmp_path / "out")]) == 0
    revealed = capsys.readouterr().out
    assert "A = " + str(a) in revealed and "B = " + str(b) in revealed
