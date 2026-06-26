# Google Antigravity SDK — Research Notes

> Research compiled 2026-06-24. Antigravity 2.0 launched at Google I/O 2026 (May 2026), which is newer than the assistant's training data, so everything here is sourced (see bottom). Focus: the **Antigravity SDK** and how to build **a simulated world where you watch agents talk to each other**.

## TL;DR

- **Antigravity 2.0** is Google's standalone, agent-first platform. Four surfaces share one **agent harness** (co-optimized with Gemini 3.5 Flash): the **desktop app**, the **Antigravity CLI**, the **Antigravity SDK** (Python), and **Managed Agents** in the Gemini API.
- The **SDK** is a Python library giving programmatic access to that same harness, deployable on your own infra. It abstracts the full agentic loop (plan → act → observe → reason).
- A "simulated world where agents talk" = a **shared message history** (the world state) + multiple **SDK agents** (the minds) + a **wake-up mechanism** (`asyncio.Condition` or `triggers`) so agents react to each other + a **frontend** to watch it.
- This pattern ships as two official `deep_dives/` examples: `round_based_chat.py` (synchronized rounds) and `async_chat.py` (emergent peer-to-peer). Google's I/O demo was a multi-agent **space-station social simulation** built exactly this way.

---

## 1. What Antigravity 2.0 is

Launched at I/O 2026 as a standalone, agent-first platform. Four surfaces, all on **one shared agent harness**:

| Surface | What it is |
|---|---|
| **Desktop app** | GUI for multi-agent orchestration |
| **Antigravity CLI** | Terminal workflow; **replaces the old Gemini CLI**. Keeps Agent Skills, Hooks, Subagents, Extensions (now "plugins"). Built-in image generation (e.g. avatar art). |
| **Antigravity SDK** | Python library — programmatic access to the same harness, deploy on your own infra |
| **Managed Agents** | Gemini API: one API call spins up an agent in a Google-hosted Linux sandbox |

Improvements to the harness propagate across all surfaces. Ecosystem integrations: Google AI Studio, Android, Firebase. Enterprise path via the **Gemini Enterprise Agent Platform**.

---

## 2. The Antigravity SDK (Python)

A Python framework to build, test, and run autonomous agents on the **same harness** as the CLI/desktop. Optimized for Gemini models.

### Install

Must come from the **PyPI wheel** — it ships a compiled runtime binary, so cloning the repo will not work.

```bash
pip install google-antigravity
export GEMINI_API_KEY="your_key"
```

Requires Python 3.10+, Linux/macOS wheels.

### Minimal agent

```python
from antigravity_sdk import Agent, LocalAgentConfig

async with Agent(LocalAgentConfig(api_key="...")) as agent:
    response = await agent.chat("What files are in the current directory?")
    print(await response.text())
```

`Agent` is an async context manager that manages the connection + session lifecycle. `chat()` runs the request-response/tool-calling cycle.

### Core building blocks — `LocalAgentConfig`

| Field / concept | Purpose |
|---|---|
| `system_instructions` | Persona / behavior. Use `TemplatedSystemInstructions` to keep SDK safety scaffolding + inject `identity`/`sections`; or `CustomSystemInstructions` to fully replace the prompt (you then handle env context manually). |
| `tools` | Plain Python functions; docstring + type hints become the tool schema. |
| `mcp_servers` | Connect external MCP tools (`McpStdioServer`). |
| `policies` | Declarative guardrails: `deny()`, `allow()`, `ask_user()`, `enforce()` to gate tool access. |
| `triggers` | Background tasks that react to events and **push** messages into an agent, e.g. `every(60, check_status)`. Key for event-driven wake-ups. |
| `capabilities` | Agent capability flags. |
| `vertex=True`, `project`, `location` | Gemini Enterprise / Vertex deployment. |

Other features:

- **Streaming** — separate async streams for final tokens, `thoughts` (chain-of-thought), and typed `tool_calls`.
- **Multimodal** — `Image`, `Document`, `from_file()` for image/video/audio/doc input + generation.
- **Subagents** — spawn child agents with their own tools/instructions/context; the building block for agent *teams*. (Subagent lifecycle hooks exist throughout the SDK.)
- **`Conversation`** — lower-level stateful session (history, turn counts, step-by-step control via `ConnectionStrategy`) when you want manual control of the loop.
- **Hooks** — lifecycle hooks for session, turn, tool, subagent, compaction, interaction (see `host_tool_hooks.py`); stackable middleware for rate-limiting, audit logging, error recovery (`agent_middleware.py`).

### Defining a tool

```python
def get_weather(city: str) -> str:
    """Returns the current weather for a city."""
    return f"It's sunny in {city}."

config = LocalAgentConfig(tools=[get_weather])
```

### Example files shipped with the SDK

Two tiers: `getting_started/` (single-feature walkthroughs — agents, streaming, tools, policies, hooks, structured output) and `deep_dives/` (complex patterns).

| Example | Concepts |
|---|---|
| `interactive_cli.py` | Custom tools, MCP servers, hook-based tool approval |
| `agent_middleware.py` | Stacked hooks: rate limiting, audit logging, error recovery |
| `host_tool_hooks.py` | All lifecycle hooks (session, turn, tool, subagent, compaction, interaction) |
| **`round_based_chat.py`** | **Multi-agent** — synchronized chat room, parallel turns, triggers |
| **`async_chat.py`** | **Multi-agent** — peer-to-peer chat with reactive wake-ups |
| `multimodal_pipeline.py` | Image generation + analysis |
| `doc_maintenance_agent.py` | Autonomous agent with scoped file policies |
| `docstring_maintenance_agent.py` | Autonomous agent with destructive tools disabled |

---

## 3. Managed Agents (Gemini API) — the hosted alternative

If you don't want to host the loop yourself, one API call provisions a secure Google-hosted Linux sandbox and starts an autonomous reasoning loop.

```python
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    agent="antigravity-preview-05-2026",
    input="Read Hacker News, summarize the top 10 stories, and save the results as a PDF.",
    environment="remote",
)
```

- `environment`: `"remote"` (fresh sandbox), an existing id like `"env_abc123"` (reuse — files/state persist), or an `EnvironmentConfig` object.
- **Multi-turn / function calling** requires stateful mode via `previous_interaction_id`:

```python
final_interaction = client.interactions.create(
    agent="antigravity-preview-05-2026",
    previous_interaction_id=interaction.id,
    environment=interaction.environment_id,
    input=[{"type": "function_result", ...}],
)
```

- **Filesystem-native customization**: mount `AGENTS.md` (instructions) and `.agents/skills/` (skills) into the sandbox; iterate, then save as a managed agent.
- Capabilities: code execution, file management, web search, custom function calling.
- Good for tool-heavy, long-running single agents; less ideal for a tight real-time many-agent room (use the local SDK for that).

---

## 4. The space-station social simulation (the I/O demo)

At I/O 2026 the Antigravity team built a **multi-agent social simulation**: virtual avatars of attendees interacting **autonomously** inside a simulated space station. The described recipe:

1. **Scaffold each agent** with the CLI; give it a **rich personality**; grant tools for real-time info.
2. **Generate its avatar** with the CLI's built-in image generation.
3. **Python backend** serves an API; the SDK agent is the "brain," and a frontend (JS / mobile / CLI) renders the world and talks to that brain over the API.

So: the **world** is your frontend + a shared message space; the **minds** are SDK agents; **talking** is agents reading a shared transcript and writing back to it.

---

## 5. The two canonical "agents talking" patterns

### A. Round-based (`round_based_chat.py`) — synchronized

- A `ChatRoom` holds one shared `history`.
- Each round, **all agents think in parallel** via `asyncio.gather()`.
- A `_last_seen` index per agent feeds each one only the messages it hasn't seen.
- Agents call a `pass_turn()` tool to stay silent; the loop ends when everyone passes or hits `_MAX_ROUNDS` (4 in the example).
- An `every(60, _moderator_nudge)` trigger prods a stalled room.
- Agent config sketch:

```python
for name, instructions in _AGENT_CONFIGS.items():
    config = LocalAgentConfig(
        system_instructions=instructions,
        tools=[pass_turn],
        triggers=[every(60, _moderator_nudge)],
    )
    agents[name] = Agent(config)
```

Personas in the example: research-focused Rita, imaginative Cal, skeptical Sam.

### B. Peer-to-peer (`async_chat.py`) — emergent, no rounds

- Each agent runs its **own independent loop**; ordering is **emergent** — whoever finishes `agent.chat()` first speaks next.
- Coordination is an **`asyncio.Condition`**: when any agent appends to shared `history`, it calls `notify_all()`; all sleeping agents wake to check what's new.
- Each agent filters out its own messages / pass tokens, so it reacts only to genuine peer content; the LLM keeps stateful context, so prompts inject only newly-arrived peer messages.
- Self-terminates via `_MAX_CONSECUTIVE_PASSES` or a 120s timeout.
- Personas in the example: Pragmatic Priya, Visionary Vince, Cautious Cora.
- **Trade-offs** (from the example docstring): no forced sync + fast agents respond immediately + naturally self-terminating; but a fast agent can dominate and agents may reply before seeing every message.

---

## 6. Build pattern — peer-to-peer chat room

Reconstruction of the `async_chat.py` architecture using the real SDK APIs. Smallest thing that gives you "watch agents talk."

```python
import asyncio
from antigravity_sdk import Agent, LocalAgentConfig

class AsyncChatRoom:
    def __init__(self):
        self.history: list[tuple[str, str]] = []   # (speaker, text) — shared world state
        self._cond = asyncio.Condition()           # wakes agents when anyone speaks
        self._done = False

    async def post(self, name: str, text: str):
        async with self._cond:
            self.history.append((name, text))
            print(f"{name}: {text}")               # the "world" you watch
            self._cond.notify_all()                # wake every other agent

    async def run_agent(self, name: str, agent: Agent):
        last_seen = 0
        async with agent:
            while not self._done:
                async with self._cond:
                    await self._cond.wait_for(
                        lambda: len(self.history) > last_seen or self._done)
                    new = [f"{s}: {t}" for s, t in self.history[last_seen:] if s != name]
                    last_seen = len(self.history)
                if not new:
                    continue
                resp = await agent.chat("New messages:\n" + "\n".join(new))
                text = (await resp.text()).strip()
                if text and text != "<pass>":
                    await self.post(name, text)

PERSONAS = {
    "Priya": "You are Pragmatic Priya. Push for concrete next steps. Reply <pass> if you have nothing to add.",
    "Vince": "You are Visionary Vince. Offer bold, imaginative ideas. Reply <pass> if nothing to add.",
    "Cora":  "You are Cautious Cora. Surface risks and edge cases. Reply <pass> if nothing to add.",
}

async def main():
    room = AsyncChatRoom()
    agents = {n: Agent(LocalAgentConfig(system_instructions=p)) for n, p in PERSONAS.items()}
    await room.post("Host", "Topic: should we colonize Mars this century?")
    await asyncio.gather(*(room.run_agent(n, a) for n, a in agents.items()))

asyncio.run(main())
```

**Scaling toward the space-station demo:**
- Swap `print()` for **WebSocket broadcasts** to a frontend.
- Give agents **spatial / "who's nearby" tools** so they only "hear" agents in the same room.
- Use a real `pass_turn()` tool instead of the `<pass>` string convention.
- Generate avatars with the CLI's image generation.

**Mental model:**
- shared `history` = the world's state
- `asyncio.Condition` / `triggers` = perception (agents wake on events)
- `system_instructions` = personality
- `tools` = how an agent affects the world
- frontend = the window you watch it through

---

## 7. Availability & caveats

- **Gemini-only** — SDK optimized for Gemini; needs `GEMINI_API_KEY` (or Vertex/Enterprise project). Every agent turn is an API call, so a busy room burns tokens fast.
- **Install from the PyPI wheel** (compiled binary) — not from source.
- **Local SDK vs Managed Agents**: local SDK for tight real-time many-agent rooms; Managed Agents for tool-heavy, long-running single agents in a Google sandbox.
- This is **2.0, post-I/O-2026** — verify specifics against current official docs as the API is still in preview (`antigravity-preview-05-2026`).

---

## Sources

- Introducing the Antigravity SDK (blog): https://antigravity.google/blog/introducing-google-antigravity-sdk
- SDK product page: https://antigravity.google/product/antigravity-sdk
- SDK docs overview: https://antigravity.google/docs/sdk-overview
- antigravity-sdk-python (GitHub): https://github.com/google-antigravity/antigravity-sdk-python
- Examples folder: https://github.com/google-antigravity/antigravity-sdk-python/tree/main/examples
- PyPI: https://pypi.org/project/google-antigravity/
- Managed Antigravity Agent — Gemini API docs: https://ai.google.dev/gemini-api/docs/antigravity-agent
- Antigravity 2.0 launch — MarkTechPost: https://www.marktechpost.com/2026/05/19/google-launches-antigravity-2-0-at-i-o-2026-a-standalone-agent-first-platform-with-cli-sdk-managed-execution-and-enterprise-support/
- Space-station social simulation (Antigravity on X): https://x.com/antigravity/status/2067668667815313620
- Building a digital simulated world (YouTube): https://www.youtube.com/watch?v=xlALU-kyFdw
- Getting started (DeepWiki): https://deepwiki.com/google-antigravity/antigravity-sdk-python/1.1-getting-started
