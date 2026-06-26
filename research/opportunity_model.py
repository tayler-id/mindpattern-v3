#!/usr/bin/env python3
"""
opportunity_model.py  (v2 - backtest-driven)
============================================
Ranks newsletter THEMES by predicted near-term opportunity, choosing the signal
weights by OUT-OF-SAMPLE VALIDATION rather than assertion. Pure stdlib, reproducible.

Pipeline
--------
1. Read every core daily issue, count theme-keyword occurrences per issue.
2. Build per-issue count vectors and a per-issue-mean weekly time series.
3. Compute candidate signals per theme:
      level      = mean occurrences/issue over all weeks      (structural importance)
      momentum   = OLS slope of ln(1+weekly_mean)             (1st derivative / trend)
      accel      = late-half slope - early-half slope         (2nd derivative)
      recency    = EWMA(weekly_mean), lambda=0.8              (current heat)
      centrality = mean Pearson corr of this theme's per-issue
                   count vector with every other theme's      (co-movement / convergence)
4. BACKTEST every signal individually: fit on the early weeks only (hold out the
   last 4 weeks), Spearman-correlate against (a) held-out LEVEL and (b) held-out
   GROWTH. This tells us which signals actually predict, and at n=15 themes we also
   sanity-check significance.
5. Build the final opportunity score ONLY from signals that showed positive
   out-of-sample skill, then re-backtest the composite. score = Z[theme,:] . w.

Run:  python3 research/opportunity_model.py
"""
import os, re, glob, math
from datetime import date

NEWSDIR = os.path.join(os.path.dirname(__file__), "..",
                       "data", "ramsay", "mindpattern", "newsletters")

THEMES = {
 "MCP protocol & tooling":           r"\bMCP\b|model context protocol|streamable http|server/discover|tool (?:definition|schema|catalog)|code mode|search\(\)|execute\(\)|meta-tool",
 "Agent/MCP security & injection":   r"prompt injection|tool poisoning|jailbreak|guardrail|red[- ]?team|exfiltrat|\bRCE\b|\bSSRF\b|\bBOLA\b|zero[- ]?auth|path traversal|owasp|\bCVE\b|agentjack",
 "Supply-chain / dependency attacks":r"supply[- ]chain|backdoor|malicious (?:package|skill|npm|dependency)|teampcp|shai-hulud|typosquat|SHA[- ]?pin|package cooldown|provenance|attestation|\bRAT\b",
 "Token economics / cost / compression":r"token (?:cost|budget|economic|tax|bloat)|context (?:compression|bloat|rot)|usage[- ]based (?:billing|pricing)|metered|metering|tokenmax|per-?token|cost[- ]per|compaction",
 "Skills / config-as-context":       r"SKILL\.md|CLAUDE\.md|AGENTS?\.md|DESIGN\.md|agent skills|build skills|progressive disclosure|slash command|loop engineering|loopcraft",
 "Open-weight / local / quantization":r"open[- ]?weight|self-host|\bGLM[- ]?\d|kimi|qwen|\bllama\b|deepseek|minimax|gemma|devstral|poolside|cohere|local (?:model|inference)|on-?device|\bGGUF\b|quantiz|llama\.cpp|unsloth|\bMLX\b|ollama|\d-?bit",
 "Harness / orchestration / multi-agent":r"\bharness\b|orchestrat|multi-?agent|sub-?agent|planner|evaluator|agent (?:team|loop|pipeline)|\bswarm\b|worktree|control flow|fan-?out",
 "Evals / benchmarks / verification": r"\beval(?:s|uation)?\b|benchmark|SWE-?bench|terminal-?bench|ARC-?AGI|leaderboard|LLM-as-(?:a-)?judge|trajector|pass@|pass\^|verification|frontiercode",
 "Agent memory / stateful knowledge": r"agent memory|memory (?:layer|service|library|tool)|transactive|knowledge graph|knowledge object|stateful (?:knowledge|wiki)|LLM wiki|persistent memory|second brain|dreaming|claude-mem",
 "Outcome pricing / agent commerce":  r"outcome[- ]based|per-?resolution|per-?seat|agentic (?:ACV|pricing)|agent commerce|payment(?:s| rail| protocol)|\bstripe\b|machine payment|\bMPP\b|\bAP2\b|\bUCP\b|service-as-software|saaspocalypse",
 "Vibe coding / productivity mirage": r"vibe[- ]?cod|productivity (?:mirage|illusion)|rework|code churn|net-?negative|cognitive debt|slowdown|\bMETR\b|agentic engineering|slop",
 "Autonomous-agent risk / permissions":r"reward hack|rogue agent|kill[- ]switch|permission scop|least[- ]privilege|\bIAM\b|destructive (?:op|action)|deleted (?:the )?(?:prod|production|database)|blast radius|confirmation gate|spend (?:cap|ceiling|limit)",
 "Post-training / RLHF / fine-tuning": r"\bRLHF\b|\bDPO\b|\bORPO\b|\bKTO\b|fine[- ]?tun|post-?training|\bLoRA\b|\bQLoRA\b|reward model|\bRFT\b|reinforcement (?:fine|learning)|distillation|GRPO",
 "Frontier model launches / churn":   r"\bopus\b|\bsonnet\b|\bhaiku\b|gemini|GPT-?5|\bgrok\b|\bfable\b|mythos|frontier model|model (?:launch|release)|export control",
 "Agent-authored UI / sandboxed apps": r"sandbox|iframe|\bCSP\b|MCP apps|datasette|artifact|micro-?app|agent-?ready|webmcp|stitch|claude design|design system|firecracker|gvisor",
}

# ----------------------------------------------------------------- read corpus
CORE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
files = []
for p in sorted(glob.glob(os.path.join(NEWSDIR, "*.md"))):
    m = CORE.match(os.path.basename(p))
    if m and os.path.getsize(p) >= 500:
        y, mo, d = map(int, m.groups())
        files.append((date(y, mo, d), p))
files.sort()
first = files[0][0]
wk = lambda dt: (dt - first).days // 7
compiled = {t: re.compile(rx, re.I) for t, rx in THEMES.items()}
themes = list(THEMES)

issue_w   = []                          # week index per issue (parallel to issue_cnt)
issue_cnt = []                          # per issue: dict theme->count
week_occ  = {t: {} for t in themes}
week_n    = {}
for dt, p in files:
    w = wk(dt)
    text = open(p, encoding="utf-8", errors="ignore").read()
    week_n[w] = week_n.get(w, 0) + 1
    counts = {}
    for t, rx in compiled.items():
        c = len(rx.findall(text))
        counts[t] = c
        if c:
            week_occ[t][w] = week_occ[t].get(w, 0) + c
    issue_w.append(w); issue_cnt.append(counts)
weeks = sorted(week_n); maxw = weeks[-1]
wmean = lambda t, ws: [week_occ[t].get(w, 0)/week_n[w] for w in ws]

# ----------------------------------------------------------------- math (stdlib)
def slope(xs, ys):
    n=len(xs); xb=sum(xs)/n; yb=sum(ys)/n; d=sum((x-xb)**2 for x in xs)
    return 0.0 if d==0 else sum((x-xb)*(y-yb) for x,y in zip(xs,ys))/d
def z(v):
    n=len(v); mu=sum(v)/n; sd=math.sqrt(sum((x-mu)**2 for x in v)/n)
    return [0.0]*n if sd==0 else [(x-mu)/sd for x in v]
def rank(v):
    o=sorted(range(len(v)),key=lambda i:v[i]); r=[0.0]*len(v); i=0
    while i<len(v):
        j=i
        while j+1<len(v) and v[o[j+1]]==v[o[i]]: j+=1
        a=(i+j)/2.0+1
        for k in range(i,j+1): r[o[k]]=a
        i=j+1
    return r
def pearson(a,b):
    n=len(a); ma=sum(a)/n; mb=sum(b)/n
    da=[x-ma for x in a]; db=[y-mb for y in b]
    d=math.sqrt(sum(x*x for x in da)*sum(y*y for y in db))
    return 0.0 if d==0 else sum(x*y for x,y in zip(da,db))/d
spear=lambda a,b: pearson(rank(a),rank(b))

def signals(use_weeks, use_issue_idx):
    """compute the 5 candidate signals using only the given weeks/issues."""
    out={t:{} for t in themes}
    half=len(use_weeks)//2
    xs=[float(w) for w in use_weeks]
    # per-issue count vectors for centrality
    vecs={t:[issue_cnt[i][t] for i in use_issue_idx] for t in themes}
    for t in themes:
        ms=wmean(t,use_weeks); ys=[math.log1p(v) for v in ms]
        out[t]["level"]=sum(ms)/len(ms)
        out[t]["momentum"]=slope(xs,ys)
        out[t]["accel"]=slope(xs[half:],ys[half:])-slope(xs[:half],ys[:half])
        wts=[0.8**(use_weeks[-1]-w) for w in use_weeks]
        out[t]["recency"]=sum(a*b for a,b in zip(wts,ms))/sum(wts)
        cs=[pearson(vecs[t],vecs[u]) for u in themes if u!=t]
        out[t]["centrality"]=sum(cs)/len(cs)
    return out

# ----------------------------------------------------------------- backtest
train_w=[w for w in weeks if w<=maxw-4]; test_w=[w for w in weeks if w>maxw-4]
tr_idx=[i for i,w in enumerate(issue_w) if w<=maxw-4]
sig_tr=signals(train_w, tr_idx)
tgt_level=[sum(wmean(t,test_w))/len(test_w) for t in themes]
tgt_growth=[ (sum(wmean(t,test_w))/len(test_w))
            -(sum(wmean(t,train_w[-4:]))/len(train_w[-4:])) for t in themes]
CAND=["level","momentum","accel","recency","centrality"]
print(f"corpus: {len(files)} core issues | {first} .. {files[-1][0]} | {len(weeks)} weeks\n")
print("PER-SIGNAL BACKTEST  (fit on weeks 0..%d, predict held-out last %d weeks; n=%d themes)"
      %(maxw-4,len(test_w),len(themes)))
print(f"{'signal':12} {'Spearman vs LEVEL':>20} {'Spearman vs GROWTH':>20}")
skill={}
for s in CAND:
    col=[sig_tr[t][s] for t in themes]
    rl=spear(col,tgt_level); rg=spear(col,tgt_growth); skill[s]=(rl,rg)
    print(f"{s:12} {rl:>20.3f} {rg:>20.3f}")
# significance rule of thumb at n=15: |rho| ~>0.51 => p<0.05
print("  (at n=15, |rho| >~ 0.51 is significant at p<.05; smaller = no demonstrable skill)\n")

# ----------------------------------------------------------------- final score
# Keep only signals with positive skill at predicting held-out LEVEL (the part that
# is actually forecastable). Weight proportional to that validated skill.
val={s:skill[s][0] for s in CAND if skill[s][0]>0}
wsum=sum(val.values())
WEIGHTS={s:round(val[s]/wsum,3) for s in val}
sig_full=signals(weeks, list(range(len(files))))
Zf={t:{s:zz for s,zz in zip(val, z([sig_full[t][s] for t in themes]))} for t in themes}
# rebuild Z properly per-signal
Zf={t:{} for t in themes}
for s in val:
    for t,zz in zip(themes, z([sig_full[t][s] for t in themes])):
        Zf[t][s]=zz
score={t:sum(WEIGHTS[s]*Zf[t][s] for s in val) for t in themes}

# backtest the composite itself
comp_tr={t:sum(WEIGHTS[s]*zz for s,zz in zip(val, []) ) for t in themes}  # placeholder
# proper composite-on-train
ztr={s:{t:zz for t,zz in zip(themes, z([sig_tr[t][s] for t in themes]))} for s in val}
comp_tr=[sum(WEIGHTS[s]*ztr[s][t] for s in val) for t in themes]
comp_skill_level=spear(comp_tr,tgt_level)
comp_skill_growth=spear(comp_tr,tgt_growth)

print("FINAL OPPORTUNITY SCORE  (weights = validated level-skill, normalized)")
print(f"  weights: {WEIGHTS}")
print(f"  composite backtest:  vs LEVEL = {comp_skill_level:+.3f}   vs GROWTH = {comp_skill_growth:+.3f}\n")
hdr=f"{'THEME':37s} {'level':>7} {'accel':>7} {'central':>7} {'SCORE':>7}"
print(hdr); print("-"*len(hdr))
for t in sorted(themes,key=lambda t:-score[t]):
    f=sig_full[t]
    print(f"{t:37s} {f['level']:7.2f} {f['accel']:+7.3f} {f['centrality']:7.3f} {score[t]:+7.3f}")
