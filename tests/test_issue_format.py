"""The issue's layout is counted in code and held to newsletter.layout (orchestrator/issue_format.py)."""
from orchestrator.editorial import Layout, load
from orchestrator.issue_format import measure, report, violations

ISSUE = """# Wire

## Top 5 stories today

### A prose story that closes on a list

First paragraph with a [link](https://x.example/1).

Second paragraph.

What to do:
- Pin the version.

- Rotate the token.
  The token lives in the vault.

---

### A story with a list in the middle

Opening paragraph.

- one
- two

Closing paragraph.

| Model | Price |
|---|---|
| A | $1 |

---

## Research

**A finding.** A paragraph.
**Why it matters:** a line.

1. a numbered list
2. inside a section

## Skills of the day

1. One skill.
2. Another skill.
"""


def test_each_top_story_and_section_is_counted():
    units = {u.heading: u for u in measure(ISSUE)}
    closing = units["A prose story that closes on a list"]
    assert (closing.kind, closing.bullets, closing.lists, closing.longest_list, closing.ends_on_list) == (
        "top", 2, 1, 2, True)
    middle = units["A story with a list in the middle"]
    assert (middle.lists, middle.tables, middle.ends_on_list) == (1, 1, False)
    assert (units["Research"].kind, units["Research"].lists) == ("section", 1)
    assert "Top 5 stories today" not in units
    assert report(ISSUE).splitlines()[-1].split()[-3:] == ["8", "4", "1"]


def test_every_breach_of_the_layout_is_named_as_a_fix():
    assert violations(ISSUE, load().layout) == [
        'layout: Top story "A story with a list in the middle" has 1 table(s) where 0 is allowed; write the '
        "table as prose",
        'layout: Top story "A story with a list in the middle" has a list before its end; fold it into prose',
        'layout: section "Research" has 1 lists where 0 is allowed; fold the extra lists into prose',
    ]


def test_a_top_story_gets_one_short_list_and_skills_of_the_day_is_exempt():
    story = "## Top 5 stories today\n\n### S\n\nProse.\n\n- a\n- b\n- c\n- d\n- e\n\nProse.\n\n- f\n"
    assert violations(story, Layout()) == [
        'layout: Top story "S" has 2 lists where 1 is allowed; fold the extra lists into prose',
        'layout: Top story "S" has a list of 5 items where 4 is allowed; fold the rest into prose',
    ]
    skills = "## Skills of the day\n\n" + "".join(f"{n}. Skill.\n" for n in range(1, 11))
    assert violations(skills, Layout()) == []
    assert violations(skills, Layout(list_sections=())) == [
        'layout: section "Skills of the day" has 1 lists where 0 is allowed; fold the extra lists into prose']
