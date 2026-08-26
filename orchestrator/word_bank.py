"""Shared word bank for every surface that publishes prose.

Before this module the project kept four ban lists that had drifted apart:

* ``data/ramsay/mindpattern/voice.md`` reached the social writers as prompt text
  and was never checked.
* ``policies/social.json`` checked eleven marketing words on social posts.
* ``orchestrator/site_copy_lint.py`` checked forty words on site stories.
* ``orchestrator/prose_gate.py`` checked em-dashes on the newsletter and nothing
  lexical at all.

So the newsletter used "landed" 27 times across 9 of the 10 August issues and
no gate saw it. The bank fixes the drift by holding every term once, tagging it
with the surfaces it applies to, and rendering the prompt text from the same
rows the gate reads. A ban the writer was never told about is a bug, and
``prompt_block()`` is what keeps that from happening.

Two tiers:

* ``ban`` the term never appears. A regex catches it.
* ``cap`` the term is legitimate but was overused. The ceiling is a rate per
  10,000 words, set at roughly half the measured August rate, so one use in a
  short post is always fine and a habit is not.

Counts in the ``note`` fields were measured over ``reports/ramsay/2026-08-14``
through ``2026-08-23``, 92,096 words of prose with headings, source lines and
the feedback footer stripped.

@know: [[orchestrator/runner#Synthesis]]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SURFACES = ("newsletter", "social", "engagement", "site")
ALL = SURFACES

VOICE_SECTION_MARKER = "## Word bank (generated, do not hand-edit)"

# Spans whose contents are never our prose: fenced code, inline code, markdown
# link and image targets, bare URLs, and anything inside straight double quotes.
# The quote rule matters most. We police the sentences we write, not the words a
# source used, and the newsletter quotes release notes constantly.
_PROTECTED = re.compile(
    r"```.*?```"
    r"|`[^`\n]*`"
    r"|\[[^\]\n]*\]\([^)\s]*\)"
    r"|<https?://[^>\s]+>"
    r"|https?://\S+"
    r"|\"[^\"\n]{0,400}\""
    r"|“[^”\n]{0,400}”",
    re.DOTALL,
)


@dataclass(frozen=True)
class Entry:
    """One banned or capped term."""

    term: str
    tier: str            # "ban" or "cap"
    pattern: str         # regex source, always compiled case-insensitive
    instead: str         # what to write in its place
    example: str         # a real sentence the pattern must match
    surfaces: tuple[str, ...] = ALL
    family: str = ""
    note: str = ""
    cap_per_10k: float = 0.0
    # How hard the site copy lint should push back. A word the writer must
    # never type is worth rejecting the draft over. A sentence shape is not:
    # rejecting costs a full regeneration, and the critic can fix a frame in
    # place, so frames come back as revision notes instead.
    site_severity: str = "fail"


@dataclass(frozen=True)
class Hit:
    entry: Entry
    count: int
    examples: tuple[str, ...] = field(default=())


# ── The bank ────────────────────────────────────────────────────────────────
#
# Family names describe the rhetorical move, because the move is what reads as
# machine-written. Banning one word from a family and leaving its four siblings
# just moves the tic.

BANK: tuple[Entry, ...] = (
    # ── Release verbs ───────────────────────────────────────────────────────
    Entry(
        term="landed",
        tier="ban",
        pattern=r"\b(?:landed|lands)\b(?!\s+(?:a|the)\s+(?:job|client|deal|plane|round|contract))",
        instead="name the actor and the plain verb: \"Kilo Code released 7.4.23 on "
                "August 20\", \"support is in 2.1.239\", \"the paper went up August 21\"",
        example="Stable core v7.4.23 landed August 20.",
        family="release verbs",
        note="61 uses across all 10 August issues, 165 across 133 site stories. "
             "The owner banned it outright on 2026-08-23, in every construction: "
             "\"this week X landed\", \"it landed like this\", \"where this landed "
             "for me\".",
    ),
    Entry(
        term="lands the same week",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:lands?|landed|arriv(?:ed|es)|dropped)\s+(?:right\s+|directly\s+"
                r"|squarely\s+|also\s+)?(?:the\s+same\s+(?:week|day)|in\s+the\s+same"
                r"\s+(?:week|day|window)|on\s+top\s+of|alongside)\b",
        instead="give both dates and say what actually connects them, or drop the "
                "link. Two things happening in one week is a coincidence until you "
                "name the mechanism.",
        example="It lands the same week Ptacek argued agents killed the TUI excuse.",
        family="release verbs",
        note="18 uses across 9 of 10 issues.",
    ),
    Entry(
        term="quietly",
        tier="ban",
        pattern=r"\bquietly\b",
        instead="say which kind of quiet and the news comes back: \"with no blog "
                "post\", \"in a changelog line nobody linked\", \"without a version bump\"",
        example="A billing bug quietly charged you twice per turn.",
        family="release verbs",
        note="22 uses across 9 of 10 issues. It claims the writer was watching "
             "when nobody else was, which is a pose, not a fact.",
    ),
    Entry(
        term="dropped a release",
        tier="ban",
        pattern=r"\b(?:dropped|drops)\s+(?:a|an|the|its|their)?\s*"
                r"(?:new\s+|updated\s+)?(?:model|models|release|version|update|"
                r"paper|repo|sdk|cli|api|feature|build|patch|preview|beta|"
                r"v?\d+\.\d)",
        instead="\"released\", \"published\", \"posted\"",
        example="OpenAI dropped a new model on Tuesday.",
        family="release verbs",
        note="Release-announcement sense only. \"Latency dropped 40%\" is untouched.",
    ),
    Entry(
        term="shipped",
        tier="cap",
        cap_per_10k=11.0,
        pattern=r"\bship(?:s|ped|ping)?\b",
        instead="use the verb for what actually happened: released, merged, "
                "tagged, published, enabled, exposed",
        example="They shipped it Tuesday.",
        family="release verbs",
        note="202 uses across all 10 issues. It is also the main replacement for "
             "\"landed\", so it needs a ceiling or it becomes the next tic.",
    ),
    Entry(
        term="hit a number",
        tier="ban",
        site_severity="revise",
        pattern=r"\bhits?\s+(?:about\s+|roughly\s+|~)?[#$]?\d",
        instead="match the verb to the number. A repo \"has 290 points\", a score "
                "\"reached 74.2\", revenue \"passed $4M\".",
        example="It hit 290 points on HN.",
        surfaces=("newsletter", "site"),
        family="release verbs",
        note="50 uses across all 10 issues.",
    ),
    Entry(
        term="metric verb plus number",
        tier="cap",
        cap_per_10k=5.0,
        pattern=r"\b(?:crossed|crosses|climbed|climbs|jumped|jumps|gained|gains"
                r"|reached|passed|sits\s+at|went\s+from)\s+(?:about\s+|roughly\s+|~)?[+#$]?\d",
        instead="pick one plain construction per kind of number and repeat it. "
                "Repetition of a plain shape reads as house style; rotating "
                "through synonyms reads as a thesaurus.",
        example="It crossed 4,000 stars.",
        surfaces=("newsletter", "site"),
        family="release verbs",
        note="99 uses across all 10 issues.",
    ),

    # ── The copular reveal ──────────────────────────────────────────────────
    #
    # "X is the <abstract noun> that Y" withholds the point, then hands it over
    # with a flourish. One an issue reads as voice. The August corpus has 110.
    Entry(
        term="is the part",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:is|isn'?t|are|aren'?t|was|wasn'?t|'s)\s+the\s+(?:\w+\s+){0,2}part\b",
        instead="name the mechanism instead of grading it. \"Preview-URL coverage "
                "is the part that closes the leak\" becomes \"Preview URLs were the "
                "leak; covering them closes it.\"",
        example="Preview-URL coverage is the part that closes the real leak.",
        family="the copular reveal",
        note="45 uses across all 10 issues, the most repeated frame in the corpus.",
    ),
    Entry(
        term="which is exactly",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:which|that)\s+is\s+exactly\b"
                r"|(?<!which )\bis\s+exactly\s+(?:what|the|why|how|where|when|backwards)\b",
        instead="end the sentence at the fact and start a new one that names what "
                "follows from it.",
        example="Direct trace reuse gets worse as traces grow, which is exactly backwards.",
        family="the copular reveal",
        note="16 uses across 8 of 10 issues.",
    ),
    Entry(
        term="is the interesting part",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:is|are|'s)\s+the\s+interesting\s+"
                r"(?:part|thing|bit|question|detail|case|move)\b"
                r"|\bwhat\s+(?:I|you)\s+find\s+interesting\b",
        instead="show the thing that makes it interesting and delete the adjective. "
                "If the reader needs to be told it is interesting, it is not.",
        example="The combination is the interesting part.",
        family="the copular reveal",
        note="7 uses across 7 of 10 issues.",
    ),
    Entry(
        term="is the real X",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:is|are|was|were|'s|'re)\s+the\s+real\s+\w+",
        instead="state the claim without the truth-modifier. \"Local-first memory "
                "is the real pitch\" becomes \"The pitch is local-first memory.\"",
        example="Local-first memory is the real pitch here.",
        family="the copular reveal",
        note="39 uses across 38 site stories, plus the newsletter's 35 uses of "
             "\"the real X\".",
    ),
    Entry(
        term="the honest X",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:an?|the|its|his|her|their|my|one|more)\s+(?:more\s+|most\s+)?"
                r"honest\s+(?:answer|version|read|reading|number|take|caveat|note|"
                r"framing|question|part|assessment)\b",
        instead="name the concession instead of grading it. \"which is the honest "
                "caveat\" becomes \"Google concedes the CPU latency is "
                "single-threaded.\"",
        example="Google quotes single-threaded latency, which is the honest caveat.",
        family="the copular reveal",
        note="26 uses across all 10 issues. Announcing your own honesty adds none.",
    ),
    Entry(
        term="the X that matters",
        tier="ban",
        site_severity="revise",
        pattern=r"\bthe\s+(?:number|claim|detail|line|one|part|question|thing|"
                r"sentence|figure|word|version|result|change|caveat|timeline)\s+"
                r"that\s+matters\b",
        instead="delete the frame and keep the content, which always survives on "
                "its own.",
        example="The claim that matters: a clean pipeline no longer costs capability.",
        family="the copular reveal",
        note="7 uses across 6 of 10 issues.",
    ),
    Entry(
        term="here's the thing",
        tier="ban",
        site_severity="revise",
        pattern=r"\bhere'?s\s+(?:the\s+thing|what|why|the\s+catch)\b",
        instead="delete it and start on the sentence that follows.",
        example="Here's the thing: the router never sees the second call.",
        family="the copular reveal",
        note="Throat-clearing. voice.md already banned it in spirit and nothing "
             "checked.",
    ),
    Entry(
        term="the copular reveal",
        tier="cap",
        cap_per_10k=5.5,
        pattern=r"\b(?:is|isn'?t|is not|are|aren'?t|was|wasn'?t|'s)\s+(?:not\s+)?the\s+"
                r"(?:\w+\s+){0,2}(?:story|point|number|pattern|mechanism|failure|signal"
                r"|gap|move|catch|tell|lesson|argument|pitch|claim|framing|premise"
                r"|detail|fix|shift|reason|difference|headline|takeaway|piece|bet"
                r"|distinction|paradox|inversion|combination)\b",
        instead="delete the predicate noun and state what the thing does. \"The "
                "model is the bottleneck\" becomes \"The model caps throughput at "
                "40 tokens a second.\"",
        example="The eval harness is the mechanism nobody looks at.",
        family="the copular reveal",
        note="110 uses across all 10 issues once every abstract noun is counted.",
    ),
    Entry(
        term=", which is",
        tier="cap",
        cap_per_10k=5.0,
        pattern=r",\s+which\s+(?:is|are|was)\b",
        instead="split it. The fact keeps the main clause, the verdict gets its "
                "own sentence with a real subject.",
        example="It caches the schema, which is the whole trick.",
        family="the copular reveal",
        note="104 uses across all 10 issues. The appraisal tag that survived the "
             "em-dash ban by moving onto a comma.",
    ),
    Entry(
        term="that's the",
        tier="cap",
        cap_per_10k=2.0,
        pattern=r"(?:^|(?<=[.!?])\s)That'?s the\b",
        instead="cut the gavel sentence, or replace it with the fact that earned "
                "the verdict.",
        example="That's the whole argument.",
        family="the copular reveal",
        note="39 uses across 8 of 10 issues.",
    ),
    Entry(
        term="the pitch is",
        tier="cap",
        cap_per_10k=1.0,
        pattern=r"\bthe\s+(?:pitch|argument|claim|framing|premise|thesis)\s+(?:is|was)\b",
        instead="name the arguer and use a real verb, or describe what the product "
                "does. \"The pitch is speed\" becomes \"Vercel says builds finish in "
                "half the time.\"",
        example="The argument is that context beats parameters.",
        family="the copular reveal",
        note="21 uses across 8 of 10 issues.",
    ),

    # ── Contrast correction ─────────────────────────────────────────────────
    Entry(
        term="not just X, it's Y",
        tier="ban",
        site_severity="revise",
        pattern=r"\bnot\s+just\s+\w[\w\s,'-]{0,60}?\b(?:it'?s|but|they'?re|that'?s)\b",
        instead="state the second half only. The first half is a strawman you "
                "wrote so you could knock it down.",
        example="This is not just a wrapper, it's a runtime.",
        family="contrast correction",
        note="In voice.md and site_copy_lint since March, never checked on the "
             "newsletter.",
    ),
    Entry(
        term=", not just X",
        tier="ban",
        site_severity="revise",
        pattern=r",\s+not just\b",
        instead="state the full instruction and let a second sentence say what "
                "the naive version misses.",
        example="Measure the session, not just the output.",
        family="contrast correction",
        note="15 uses across all 10 issues.",
    ),
    Entry(
        term="less about X than",
        tier="ban",
        site_severity="revise",
        pattern=r"\bless\s+about\s+\w[\w\s'-]{0,40}?\s+than\b",
        instead="say what it is about, in one clause.",
        example="This is less about speed than about who owns the context.",
        family="contrast correction",
        note="The em-dash-free descendant of the same reveal move.",
    ),
    Entry(
        term="X, not Y",
        tier="cap",
        cap_per_10k=7.0,
        pattern=r",\s+not\s+(?!just\b|only\b|yet\b|surprisingly\b|because\b|necessarily\b)"
                r"[a-z0-9\"']",
        instead="ask whether anyone actually held the retracted reading. If not, "
                "delete the clause and state the fact positively.",
        example="It is a scheduler, not a runtime.",
        family="contrast correction",
        note="132 uses across all 10 issues, 784 across 441 site stories.",
    ),
    Entry(
        term="rather than",
        tier="cap",
        cap_per_10k=12.0,
        pattern=r"\brather than\b",
        instead="end the sentence and start a new one, or name the swap directly.",
        example="It caches the plan rather than the result.",
        family="contrast correction",
        note="226 uses across all 10 issues, the highest-volume frame measured.",
    ),
    Entry(
        term="instead of",
        tier="cap",
        cap_per_10k=5.5,
        pattern=r"\binstead of\b",
        instead="same fix as \"rather than\": split into two sentences, or name "
                "the swap once.",
        example="It streams tokens instead of buffering the response.",
        family="contrast correction",
        note="103 uses across all 10 issues.",
    ),
    Entry(
        term="isn't X, it's Y",
        tier="cap",
        cap_per_10k=0.5,
        pattern=r"\b(?:isn'?t|is not|aren'?t|wasn'?t|weren'?t)\s+(?:the\s+|an?\s+)?"
                r"[\w-]+(?:\s+[\w-]+){0,4},\s*it'?s\b",
        instead="lead with the true half and drop the strawman.",
        example="The bottleneck isn't the model, it's the retrieval step.",
        family="contrast correction",
        note="10 uses across 6 of 10 issues.",
    ),
    Entry(
        term="versus",
        tier="cap",
        cap_per_10k=3.5,
        pattern=r"\bversus\b|\bvs\.?(?=\s)",
        instead="say which number is the claim and which is the control, which "
                "\"versus\" hides.",
        example="74.2 versus 68.1 on the same suite.",
        surfaces=("newsletter", "site"),
        family="contrast correction",
        note="66 uses across all 10 issues.",
    ),

    # ── Stance adverbs ──────────────────────────────────────────────────────
    Entry(
        term="genuinely",
        tier="ban",
        pattern=r"\bgenuinely\b",
        instead="delete it. If the adjective then feels too weak, the adjective "
                "was wrong, so replace it with the measurement.",
        example="That's a genuinely better division of labor.",
        family="stance adverbs",
        note="21 uses across 7 of 10 issues.",
    ),
    Entry(
        term="what X actually does",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:what|which|whether)\b(?:\s+\S+){0,5}?\s+actually\b",
        instead="delete the word. \"what the code actually does\" becomes \"what "
                "the code does\". If it is marking a contrast, name the contrast.",
        example="It steers the agent away from what the code actually does.",
        surfaces=("newsletter", "site"),
        family="stance adverbs",
        note="79 uses of \"actually\" across all 10 issues, most in this frame. "
             "Banned on long-form only: in a first-person post \"might actually "
             "fix it\" is speech, so social gets a cap instead.",
    ),
    Entry(
        term="actually (in a post)",
        tier="cap",
        cap_per_10k=50.0,
        pattern=r"\bactually\b",
        instead="once a post is voice. Twice is a verbal tic, so cut the weaker "
                "one or name the contrast it was gesturing at.",
        example="It might actually fix the thing.",
        surfaces=("social", "engagement"),
        family="stance adverbs",
        note="Short posts get one use. The long-form ban is stricter because the "
             "newsletter uses it as an analytical hinge, not as speech.",
    ),
    Entry(
        term="worth noting",
        tier="ban",
        pattern=r"\b(?:worth|important)\s+(?:noting|mentioning|remembering|flagging"
                r"|pointing\s+out)\b",
        instead="delete the frame and state the thing.",
        example="Worth noting that the limit resets at midnight UTC.",
        family="stance adverbs",
        note="In voice.md as a banned phrase since March, never checked anywhere.",
    ),
    Entry(
        term="roughly",
        tier="cap",
        cap_per_10k=5.0,
        pattern=r"\broughly\s+(?=[$€£~]?\d|one\b|two\b|three\b|four\b|five\b|half\b|double\b)",
        instead="if the source stated the figure, use it exactly. If you are "
                "rounding, say the real number and round in the reader's head.",
        example="Roughly 40% of the calls time out.",
        family="stance adverbs",
        note="101 uses across all 10 issues.",
    ),
    Entry(
        term="the actual X",
        tier="cap",
        cap_per_10k=1.6,
        pattern=r"\b(?:the|your|its|their|our|an?)\s+actual\s+\w+",
        instead="keep it only when the thing it contrasts with is named in the "
                "same sentence. Otherwise delete \"actual\".",
        example="The actual cost is in the retry loop.",
        family="stance adverbs",
        note="29 uses across 9 of 10 issues.",
    ),

    # ── Appraisal tags ──────────────────────────────────────────────────────
    Entry(
        term="worth stealing",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:steal|steals|stealing|stole)\b(?!\s+(?:credential|credentials"
                r"|data|token|tokens|key|keys|secret|secrets|password|passwords|funds"
                r"|money|cookies))",
        instead="name the mechanism and stop. \"The mechanic worth stealing is "
                "self-verification\" becomes \"It re-runs its own check before "
                "returning.\"",
        example="Steal that even if you never install this.",
        family="appraisal tags",
        note="19 uses across all 10 issues. Security senses (stealing credentials) "
             "are exempt.",
    ),
    Entry(
        term="what to do with this:",
        tier="ban",
        site_severity="revise",
        pattern=r"(?im)(?:^|(?<=[.!?]\s))(?:What (?:to do|you can do|I'?d(?: actually)? do)"
                r"[^:\n]{0,40}|Practical advice|The (?:audit|move|thing|action|fix) to "
                r"[^:\n]{0,30}):",
        instead="delete the label and the colon, then write the advice as a plain "
                "sentence.",
        example="What to do with this: pin your agent version before Friday.",
        family="appraisal tags",
        note="10 uses across 6 of 10 issues. The colon label announces advice "
             "instead of giving it.",
    ),
    Entry(
        term="worth watching",
        tier="cap",
        cap_per_10k=5.0,
        pattern=r"\b(?:worth watching|watch(?:ing)?\s+(?:whether|for whether)"
                r"|the\s+(?:thing|one|number|part|question|signal|metric)\s+to watch)\b",
        instead="make a prediction with a subject and a stake, or stop on the last "
                "fact.",
        example="Worth watching whether the fee survives Q4.",
        family="appraisal tags",
        note="185 uses across 180 site stories.",
    ),
    Entry(
        term="worth <gerund>",
        tier="cap",
        cap_per_10k=2.8,
        pattern=r"\bworth\s+(?:copying|reading|noticing|keeping|restating|logging"
                r"|remembering|testing|checking|knowing|having|wiring|tracking|studying"
                r"|owning|holding|grabbing|carrying|acting|adding|writing|benchmarking)\b",
        instead="delete the appraisal and let the mechanism carry it. \"The part "
                "worth copying is the retry\" becomes \"It retries once on a 429, "
                "then gives up.\"",
        example="Two details worth copying here.",
        family="appraisal tags",
        note="52 uses across all 10 issues.",
    ),
    Entry(
        term="the X to <verb>",
        tier="cap",
        cap_per_10k=0.65,
        pattern=r"\bthe\s+(?:part|number|pattern|thing|detail|move|bet|shift|one|piece"
                r"|fix|line|question|lesson|version|design|method|property)\s+to\s+"
                r"(?:steal|copy|track|watch|verify|budget|design|change|test|price"
                r"|read|fix|internalize|remember|take)\b",
        instead="give the imperative and the mechanism in one move.",
        example="The number to track is p99, not the mean.",
        family="appraisal tags",
        note="13 uses across 9 of 10 issues.",
    ),

    # ── Reader address ──────────────────────────────────────────────────────
    Entry(
        term="If you / If your (sentence opener)",
        tier="cap",
        cap_per_10k=6.0,
        pattern=r"(?m)(?:^|(?<=[.!?]\s))If your?\b",
        instead="lead with the fact and let the reader recognise themselves in it.",
        example="If you run agents in CI, this changes your budget.",
        family="reader address",
        note="121 uses across all 10 issues, and 48 of them are the closing "
             "sentence of a story.",
    ),
    Entry(
        term="check your X",
        tier="cap",
        cap_per_10k=1.1,
        pattern=r"\b(?:check|audit|measure|verify|re-verify)\s+your\b",
        instead="report where the problem actually sat and let the reader draw "
                "the inspection for themselves.",
        example="Check your config before the next deploy.",
        family="reader address",
        note="22 uses across 9 of 10 issues.",
    ),
    Entry(
        term="your own",
        tier="cap",
        cap_per_10k=1.9,
        pattern=r"\byour own\b",
        instead="delete \"own\" unless the sentence names what it is being "
                "contrasted against.",
        example="Run it against your own corpus first.",
        family="reader address",
        note="39 uses across 9 of 10 issues.",
    ),
    Entry(
        term="self-labeling closer",
        tier="cap",
        cap_per_10k=1.4,
        pattern=r"(?m)^(?:\*\*)?(?:What to do\b|What I'?d do\b|Do this today\b"
                r"|Here'?s what I'?d\b|My honest read\b|The (?:strategic|honest"
                r"|uncomfortable) (?:read|part|framing|question)\b|Action item\b)",
        instead="delete the label and start on the instruction or the uncertainty "
                "itself.",
        example="My honest read is that nobody has measured this.",
        surfaces=("newsletter", "site"),
        family="reader address",
        note="26 uses across 9 of 10 issues.",
    ),

    # ── Number narration ────────────────────────────────────────────────────
    Entry(
        term="N points and N comments",
        tier="ban",
        site_severity="revise",
        pattern=r"\b\d[\d,]*\s+(?:points|upvotes)\s+(?:and|with|against|on)\s+"
                r"\d[\d,]*\s+comments\b|\b\d[\d,]*\s+comments\s+(?:and|with|against|on)"
                r"\s+\d[\d,]*\s+(?:points|upvotes)\b",
        instead="one counter maximum, and only when the number carries a claim. "
                "If the thread matters, read it and name the disagreement.",
        example="It has 290 points and 118 comments.",
        surfaces=("newsletter", "site"),
        family="number narration",
        note="32 uses across 9 of 10 issues.",
    ),
    Entry(
        term="N stars and N forks",
        tier="ban",
        site_severity="revise",
        pattern=r"\b\d[\d,]*\s+stars(?:\s*,|\s+and|\s+against)\s+\d[\d,]*\s+forks\b"
                r"|\b\d[\d,]*\s+forks(?:\s*,|\s+and|\s+against)\s+\d[\d,]*\s+stars\b",
        instead="one counter, and only when it supports the claim the sentence "
                "is making.",
        example="The repo has 4,100 stars and 260 forks.",
        surfaces=("newsletter", "site"),
        family="number narration",
        note="11 uses across 5 of 10 issues.",
    ),
    Entry(
        term="from X to Y",
        tier="cap",
        cap_per_10k=3.4,
        pattern=r"\bfrom\s+\$?\d[\d,]*(?:\.\d+)?%?\s+to\s+\$?\d[\d,]*(?:\.\d+)?%?",
        instead="the cap is on the sentence shape, never on the numbers. Both "
                "figures stay; vary how you attach them.",
        example="Accuracy went from 68.1 to 74.2.",
        surfaces=("newsletter", "site"),
        family="number narration",
        note="63 uses across all 10 issues.",
    ),
    Entry(
        term="the same week",
        tier="cap",
        cap_per_10k=1.7,
        pattern=r"\bthe same (?:week|day|window|month|24 hours|48 hours|72 hours)\b",
        instead="name the dates, and name the reason the items count as "
                "independent evidence.",
        example="Both shipped in the same week.",
        family="number narration",
        note="32 uses across 9 of 10 issues.",
    ),
    Entry(
        term="N stars in a day",
        tier="cap",
        cap_per_10k=1.4,
        pattern=r"\b(?:stars|forks|commits|upvotes|points|downloads)\b[^.\n]{0,25}?"
                r"\b(?:in|within|over|since)\s+(?:a|one|the first|under a|less than a"
                r"|\d[\d,]*|two|three|24|48|72)\s*(?:hour|hours|day|days|week|weeks)\b",
        instead="lead with what the repo does. Use velocity only when it is the "
                "claim.",
        example="It added 2,221 stars in a day.",
        surfaces=("newsletter", "site"),
        family="number narration",
        note="26 uses across 8 of 10 issues.",
    ),

    # ── Convergence claims ──────────────────────────────────────────────────
    Entry(
        term="the same thing from different directions",
        tier="ban",
        site_severity="revise",
        pattern=r"\b(?:say(?:s|ing)?|reach(?:es|ing)?|describ\w+|arriv\w+ at)\b"
                r"[^.!?]{0,40}\bthe same (?:thing|point|phenomenon|conclusion|thesis)\b"
                r"[^.!?]{0,40}\bfrom (?:completely )?(?:different|opposite) "
                r"(?:directions|angles|ends)\b",
        instead="show the convergence instead of asserting it. Name each source, "
                "name the shared claim, and let the reader see them agree.",
        example="Three results say the same thing from completely different directions.",
        family="convergence claims",
        note="8 uses across 6 of 10 issues.",
    ),
    Entry(
        term="convergence pivot",
        tier="cap",
        cap_per_10k=1.1,
        pattern=r"(?im)^(?:And\s+)?(?:(?:This|That|It)\s+(?:converges?|connects?|rhymes?)"
                r"\b[^.\n]{0,70}|(?:Two|Three|Four|Five)\s+(?:other|related|separate"
                r"|independent|more|papers|results|findings|things|groups|vendors|teams)"
                r"\b[^.\n]{0,90}\b(?:the same (?:week|window|day|thing|direction)"
                r"|point(?:ing|s)?\s+(?:at\s+)?the same|rhymes?|converg\w+)\b)",
        instead="cut the announcement and put the facts next to each other. If two "
                "findings agree, the reader sees it without being told.",
        example="Three separate results point at the same week.",
        surfaces=("newsletter", "site"),
        family="convergence claims",
        note="20 uses across all 10 issues.",
    ),

    # ── Provenance and self-reference ───────────────────────────────────────
    Entry(
        term="the August N briefing",
        tier="ban",
        pattern=r"\bbriefings?\b",
        instead="cite the event's own source and date. A site reader has never "
                "seen the newsletter, so \"the August 17 briefing\" points at "
                "nothing they can open.",
        example="The decline is worth flagging from the August 17 briefing.",
        surfaces=("site",),
        family="provenance",
        note="160 uses across 150 of 661 site stories, zero legitimate. The site "
             "story cites the internal newsletter as though it were a public "
             "source. Same class of leak as the internal_machinery lint already "
             "catches for \"pipeline\" and \"evidence pack\".",
    ),
    Entry(
        term=", per <source>",
        tier="cap",
        cap_per_10k=21.0,
        pattern=r",\s+per\s+(?:the|a|an|its|their|his|her|authors?|arXiv\b|[A-Z][\w.\-]*)",
        instead="one trailing attribution per story, and only when the source is "
                "a named outlet or a person. \"per the paper\" and \"per the repo\" "
                "name no locator, so give the figure and the link instead.",
        example="Throughput tripled, per the paper.",
        surfaces=("site", "newsletter"),
        family="provenance",
        note="827 uses across 542 of 661 site stories, 162 of them the "
             "locator-free \"per the paper\" or \"per the repo\".",
    ),
    Entry(
        term="That's a/an/the",
        tier="cap",
        cap_per_10k=7.0,
        pattern=r"(?:^|(?<=[.!?]\s)|(?<=\n))That'?s\s+(?:a|an|the)\b",
        instead="put the subject in the sentence that makes the claim and delete "
                "the verdict sentence.",
        example="That's a real change in how the router behaves.",
        family="the copular reveal",
        note="354 uses, including 708 sentence openings across 661 site stories "
             "that begin on a bare backward demonstrative.",
    ),

    # ── Voice tics ──────────────────────────────────────────────────────────
    Entry(
        term="I keep coming back to",
        tier="ban",
        pattern=r"\b(?:i\s+keep\s+coming\s+back\s+to|the\s+thing\s+i\s+keep\s+coming"
                r"\s+back\s+to|i\s+come\s+back\s+to)\b",
        instead="name what made you look twice.",
        example="The thing I keep coming back to is the eval gap.",
        surfaces=("social", "engagement", "site"),
        family="voice tics",
        note="Listed in voice.md as an overused tic, never checked.",
    ),
    Entry(
        term="caught my attention",
        tier="cap",
        cap_per_10k=250.0,
        pattern=r"\b(?:caught|catches)\s+(?:my|me)\b",
        instead="say what you did next. \"I read the diff\" beats \"here's what "
                "caught me\".",
        example="Here's what caught me.",
        surfaces=("social", "engagement"),
        family="voice tics",
        note="The brand line is \"a builder sharing what caught their attention\", "
             "so every writer opens with it. Once a post is voice, twice is a "
             "template.",
    ),
    Entry(
        term="I run N agents",
        tier="cap",
        cap_per_10k=250.0,
        pattern=r"\bI run \d+ (?:\w+ ){0,2}agents\b",
        instead="give the lesson without the count. Agent counts are pipeline "
                "flexing, which voice.md already bans as a credibility move.",
        example="I run 13 research agents every morning.",
        surfaces=("social", "engagement"),
        family="voice tics",
        note="46 uses across 46 posts.",
    ),
)


# ── Reading ────────────────────────────────────────────────────────────────


def entries_for(surface: str) -> list[Entry]:
    """Every entry that applies to one surface."""
    return [e for e in BANK if surface in e.surfaces]


def _unprotected(text: str) -> str:
    """Text with code, links, URLs and quotations blanked out.

    Spans become spaces of the same length so offsets stay usable and no two
    words are accidentally joined across a removed span.
    """
    out = list(text)
    for match in _PROTECTED.finditer(text):
        for i in range(match.start(), match.end()):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _sentence_around(text: str, index: int) -> str:
    """The sentence holding ``index``, whitespace collapsed."""
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
    end = text.find(".", index)
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())


def scan(text: str, surface: str) -> list[Hit]:
    """Count every bank term present in one surface's prose.

    Counts only unprotected prose, so a term inside code, a link, a URL or a
    quotation is not a hit.
    """
    prose = _unprotected(text)
    hits: list[Hit] = []
    for entry in entries_for(surface):
        matches = list(re.finditer(entry.pattern, prose, re.IGNORECASE))
        if not matches:
            continue
        # Excerpt from the masked text, not the original: a bare URL blanked
        # for matching still carries dots, and pulling from the raw string put
        # half a changelog slug in front of every log line.
        examples = tuple(
            _sentence_around(prose, m.start()) for m in matches[:3]
        )
        hits.append(Hit(entry=entry, count=len(matches), examples=examples))
    return hits


def violations(text: str, surface: str) -> list[str]:
    """Human-readable failures. Empty list means the copy passes.

    A ``ban`` fails on the first hit. A ``cap`` fails only when the rate clears
    its ceiling, and never on a single use, so a 40-word post is never rejected
    for a limit expressed per 10,000 words.
    """
    words = max(len(text.split()), 1)
    out: list[str] = []
    for hit in scan(text, surface):
        entry = hit.entry
        if entry.tier == "ban":
            out.append(
                f"banned: \"{entry.term}\" x{hit.count} "
                f"({hit.examples[0] if hit.examples else ''}) "
                f"-> {entry.instead}"
            )
            continue
        allowed = max(1, int(entry.cap_per_10k * words / 10_000))
        if hit.count > allowed:
            rate = hit.count * 10_000 / words
            out.append(
                f"over cap: \"{entry.term}\" x{hit.count} in {words} words "
                f"({rate:.1f} per 10k, ceiling {entry.cap_per_10k:.0f}) "
                f"-> {entry.instead}"
            )
    return out


# ── Writing the prompt ──────────────────────────────────────────────────────


def prompt_block(surface: str) -> str:
    """Render the bank as prompt text for one surface.

    Every gate the writers face is stated here first. Rendering both from the
    same rows is the point: a term can never be enforced by a check the prompt
    did not mention.
    """
    entries = entries_for(surface)
    if not entries:
        return ""

    families: dict[str, list[Entry]] = {}
    for entry in entries:
        families.setdefault(entry.family or "other", []).append(entry)

    lines = [
        "### Never write these",
        "",
        "Measured across the last ten published issues. Each line gives the "
        "replacement, because a ban with no replacement makes prose worse.",
        "",
    ]
    for family, rows in families.items():
        lines.append(f"**{family.capitalize()}.**")
        for entry in rows:
            lines.append(f"- \"{entry.term}\". {_rule(entry)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cap_label(cap: float) -> str:
    """A cap reads as a count, so never round it down to zero."""
    return f"{cap:g}" if cap < 2 else f"{cap:.0f}"


def _rule(entry: Entry) -> str:
    """One line of guidance: the limit, then the replacement."""
    instead = entry.instead[0].upper() + entry.instead[1:] if entry.instead else ""
    if entry.tier == "ban":
        return f"Never. Write instead: {instead}"
    return (
        f"At most {_cap_label(entry.cap_per_10k)} per 10,000 words, so at most "
        f"once in a short post. {instead}"
    )


def voice_section() -> str:
    """The block written into voice.md, marker included.

    One deduped list, not one per surface. voice.md is the human-facing
    reference and gets read end to end; the per-surface detail is injected into
    each writer's prompt by ``prompt_block`` at run time.
    """
    parts = [
        VOICE_SECTION_MARKER,
        "",
        "Rendered from `orchestrator/word_bank.py`. Edit the module, then run",
        "`python3 -m orchestrator.word_bank --write-voice`. These rows also run as a",
        "deterministic gate on the newsletter, social posts, engagement replies and",
        "site stories, so everything here is measured, not just requested.",
        "",
        "Counts come from the ten issues published 2026-08-14 through 2026-08-23.",
        "",
    ]

    families: dict[str, list[Entry]] = {}
    for entry in BANK:
        families.setdefault(entry.family or "other", []).append(entry)

    for family, rows in families.items():
        parts.append(f"### {family.capitalize()}")
        parts.append("")
        for entry in rows:
            scope = (
                "" if set(entry.surfaces) == set(SURFACES)
                else f" ({', '.join(entry.surfaces)} only)"
            )
            parts.append(f"- **{entry.term}**{scope}. {_rule(entry)}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _write_voice() -> None:
    """Replace the generated section in voice.md, leaving the hand-written rest."""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "ramsay" / \
        "mindpattern" / "voice.md"
    text = path.read_text()
    section = voice_section()

    if VOICE_SECTION_MARKER in text:
        head, _, tail = text.partition(VOICE_SECTION_MARKER)
        # The generated section runs to the next H2 or to end of file.
        rest = re.split(r"\n(?=## )", tail, maxsplit=1)
        remainder = "\n" + rest[1] if len(rest) > 1 else ""
        path.write_text(head + section + remainder)
    else:
        path.write_text(text.rstrip() + "\n\n" + section)
    print(f"wrote word bank section to {path}")


if __name__ == "__main__":
    import sys

    if "--write-voice" in sys.argv:
        _write_voice()
    else:
        for _surface in SURFACES:
            print(f"===== {_surface} =====")
            print(prompt_block(_surface))
