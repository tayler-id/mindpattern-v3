"""MCP server exposing memory module as tools.

Run as stdio server:
    python3 -m mcp.memory_server

Add to Claude Code's MCP config:
    {
        "mcpServers": {
            "mindpattern-memory": {
                "command": "python3",
                "args": ["-m", "mcp.memory_server"],
                "cwd": "/Users/taylerramsay/Projects/mindpattern-v3"
            }
        }
    }
"""

import json
import logging
import sys
from pathlib import Path

# Add project root to path so `import memory` works
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

import memory

logger = logging.getLogger(__name__)

server = Server("mindpattern-memory")


# ── Tool definitions ──────────────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_findings",
            description=(
                "Semantic search across research findings using embeddings. "
                "Returns findings ranked by cosine similarity to the query."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10).",
                        "default": 10,
                    },
                    "agent": {
                        "type": "string",
                        "description": "Optional agent name filter (e.g. 'news-researcher').",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Optional filter to only search the last N days.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_context",
            description=(
                "Get full memory context for a specific agent before dispatch. "
                "Includes recent findings, top sources, overlap detection, "
                "self-improvement notes, validated patterns, and cross-pipeline signals."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": (
                            "Agent name to generate context for "
                            "(e.g. 'news-researcher', 'orchestrator')."
                        ),
                    },
                    "date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD) for context. Defaults to today.",
                    },
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="search_skills",
            description=(
                "Semantic search across actionable skills extracted from research. "
                "Returns skills ranked by similarity with optional domain filter."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query for skills.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 10).",
                        "default": 10,
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional domain filter. Valid domains: vibe-coding, "
                            "prompt-engineering, agent-patterns, ai-productivity, "
                            "ml-ops, agent-security."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_stats",
            description=(
                "Get database statistics including counts for all major tables, "
                "breakdowns by agent, date, importance, domain, and platform."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="recent_failures",
            description=(
                "Get recent failure lessons from the RetroAgent pattern. "
                "Each lesson records what went wrong and an actionable takeaway. "
                "Useful for agents to avoid repeating past mistakes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of failure lessons to return (default 10).",
                        "default": 10,
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Optional category filter (e.g. 'scraping', 'dedup', "
                            "'quality', 'timeout')."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_signal_context",
            description=(
                "Get cross-pipeline signal context as markdown. Shows signals from "
                "research, social, and feedback pipelines that should influence "
                "each other. Positive strength = more coverage, negative = less."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 14).",
                        "default": 14,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="query_entity",
            description=(
                "Query the entity graph for all relationships involving a specific "
                "entity. Returns related entities, relationship types, and linked "
                "findings. Entities include people, companies, tools, and concepts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to query (e.g. 'OpenAI', 'Claude', 'Anthropic').",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_preferences",
            description=(
                "List user topic preferences with optional temporal decay. "
                "Preferences are accumulated from email feedback. "
                "Positive weight = user wants more coverage, negative = less."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Filter to preferences for a specific email address.",
                    },
                    "effective": {
                        "type": "boolean",
                        "description": (
                            "If true, include effective_weight with temporal decay applied "
                            "(half-life ~14 days). Default false."
                        ),
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    db = memory.get_db()
    try:
        result = _dispatch(name, arguments, db)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(exc), "tool": name}),
        )]
    finally:
        db.close()


def _dispatch(name: str, args: dict, db) -> object:
    """Route a tool call to the appropriate memory function.

    Args:
        name: Tool name from the MCP request.
        args: Tool arguments from the MCP request.
        db: Open sqlite3.Connection to memory.db.

    Returns:
        JSON-serializable result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    if name == "search_findings":
        return memory.search_findings(
            db,
            query=args["query"],
            limit=args.get("limit", 10),
            agent=args.get("agent"),
            days=args.get("days"),
        )

    elif name == "get_context":
        return memory.get_context(
            db,
            agent=args["agent"],
            date=args.get("date"),
        )

    elif name == "search_skills":
        return memory.search_skills(
            db,
            query=args["query"],
            limit=args.get("limit", 10),
            domain=args.get("domain"),
        )

    elif name == "get_stats":
        return memory.get_stats(db)

    elif name == "recent_failures":
        return memory.recent_failures(
            db,
            limit=args.get("limit", 10),
            category=args.get("category"),
        )

    elif name == "get_signal_context":
        return memory.get_signal_context(
            db,
            days=args.get("days", 14),
        )

    elif name == "query_entity":
        return memory.query_entity(
            db,
            name=args["name"],
        )

    elif name == "list_preferences":
        return memory.list_preferences(
            db,
            email=args.get("email"),
            effective=args.get("effective", False),
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


# ── Entry point ───────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    asyncio.run(main())
