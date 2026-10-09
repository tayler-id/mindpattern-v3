"""tools/site_backfill.py writes past issues' missing site stories, optionally with no Codex calls."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("site_backfill_tool", ROOT / "tools" / "site_backfill.py")
tool = importlib.util.module_from_spec(SPEC)
sys.modules["site_backfill_tool"] = tool
SPEC.loader.exec_module(tool)

ISSUE = """# Ramsay Research Agent — July 2, 2026

## Security

**OpenAI ships agent controls for every workspace.** [OpenAI](https://openai.com/news/controls)
released new controls. Full body sentence about the release with detail.

**Anthropic adds memory tools for teams this week.** [Anthropic](https://anthropic.com/news/memory)
shipped memory tooling. Another full body sentence with enough detail here.
"""


def _copy(pack, experts):
    return {"title": f"Written {pack['candidate_id'][:20]}", "dek": "A dek for the story.",
            "take": "A take with a claim.", "why_now": "It shipped today.",
            "body_markdown": "Body.\n\nMore body."}


def test_each_date_gets_its_missing_stories_up_to_the_cap(tmp_path):
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE)
    outcomes = tool.backfill(["2026-07-02"], user="ramsay", reports_root=tmp_path, copywriter=_copy, cap=1)
    assert [(o["date"], o["written"], o["skipped"]) for o in outcomes] == [("2026-07-02", 1, 0)]
    again = tool.backfill(["2026-07-02"], user="ramsay", reports_root=tmp_path, copywriter=_copy, cap=2)
    assert [(o["written"], o["skipped"]) for o in again] == [(1, 1)]


def test_the_claude_critic_switch_routes_only_the_critic_and_undoes_itself():
    from core.config import route_for
    from orchestrator import site_critic

    before = site_critic.route_for("site_story_critic")
    assert before.provider == "codex"
    with tool.claude_critic():
        assert site_critic.route_for("site_story_critic") == before.fallback
        assert site_critic.route_for("site_story_writer") == route_for("site_story_writer")
    assert site_critic.route_for("site_story_critic") == before
