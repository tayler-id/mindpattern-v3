"""Configuration constants for the knowledge compiler."""

from pathlib import Path

# Project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Vault paths
VAULT_DIR = ROOT_DIR / "data" / "ramsay" / "mindpattern"
KNOWLEDGE_DIR = VAULT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
CONVERSATIONS_DIR = KNOWLEDGE_DIR / "conversations"
SESSIONS_DIR = KNOWLEDGE_DIR / "sessions"
INDEX_PATH = KNOWLEDGE_DIR / "index.md"
LOG_PATH = KNOWLEDGE_DIR / "log.md"
AGENTS_MD = ROOT_DIR / "knowledge" / "AGENTS.md"

# Database
DB_PATH = ROOT_DIR / "data" / "ramsay" / "memory.db"

# State files
STATE_DIR = ROOT_DIR / "knowledge" / "state"
STATE_JSON = STATE_DIR / "state.json"
LAST_FLUSH_JSON = STATE_DIR / "last-flush.json"
FLUSH_LOG = STATE_DIR / "flush.log"
COMPILE_LOG = STATE_DIR / "compile.log"

# Limits
MAX_CONTEXT_CHARS = 15000
MAX_TURNS_TO_CAPTURE = 30
MIN_TURNS_SESSION_END = 2
MIN_TURNS_PRE_COMPACT = 5
DEDUP_WINDOW_SECONDS = 60
