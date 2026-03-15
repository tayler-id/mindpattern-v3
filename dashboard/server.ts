/**
 * mindpattern pipeline dashboard — real-time monitoring
 *
 * Bun WebSocket server + static HTML dashboard.
 * Shows running processes, live log events, artifacts, images, drafts.
 *
 * Usage: bun run dashboard/server.ts
 */

import { readFileSync, existsSync, statSync, readdirSync } from "fs";
import { join, resolve } from "path";
import { Database } from "bun:sqlite";

const PROJECT_DIR = resolve(import.meta.dir, "..");
const DATA_DIR = join(PROJECT_DIR, "data");
const REPORTS_DIR = join(PROJECT_DIR, "reports");
const DRAFTS_DIR = join(DATA_DIR, "social-drafts");
const DB_PATH = join(DATA_DIR, "ramsay", "memory.db");
const PORT = 3333;

// ── Process scanner ──────────────────────────────────────────────────────

interface ProcessInfo {
  type: string;
  name: string;
  pid: string;
  cpu: string;
  mem: string;
  started: string;
}

async function scanProcesses(): Promise<ProcessInfo[]> {
  try {
    const result = await $`ps aux`.text();
    const lines = result.split("\n");
    const procs: ProcessInfo[] = [];

    for (const line of lines) {
      if (line.includes("grep")) continue;
      const parts = line.trim().split(/\s+/);
      if (parts.length < 11) continue;

      let entry: Partial<ProcessInfo> | null = null;

      if (line.includes("run-social.sh")) {
        entry = { type: "social", name: "Social Pipeline" };
      } else if (line.includes("run-engagement.sh")) {
        entry = { type: "engagement", name: "Engagement Pipeline" };
      } else if (line.includes("run-user-research.sh")) {
        entry = { type: "research", name: "Research Pipeline" };
      } else if (line.includes("run-all-users.sh")) {
        entry = { type: "research", name: "Research (All Users)" };
      } else if (line.includes("claude -p") && !line.includes("--session-id")) {
        // Agent subprocess
        const lower = line.toLowerCase();
        let agentType = "unknown";
        for (const kw of ["illustrator", "art-director", "creative-director",
          "curator", "writer", "critic", "engagement-finder", "engagement-writer",
          "orchestrator"]) {
          if (lower.includes(kw)) { agentType = kw; break; }
        }
        if (agentType === "unknown") continue;
        entry = { type: "agent", name: `Agent: ${agentType}` };
      }

      if (entry) {
        procs.push({
          ...entry,
          pid: parts[1],
          cpu: parts[2],
          mem: parts[3],
          started: parts[8],
        } as ProcessInfo);
      }
    }
    return procs;
  } catch {
    return [];
  }
}

// ── Log reader ───────────────────────────────────────────────────────────

interface LogEvent {
  ts: string;
  level: string;
  pipeline: string;
  stage: string;
  msg: string;
}

function readLogs(pipeline: string, limit = 40): LogEvent[] {
  const date = new Date().toISOString().split("T")[0];
  const logFiles: Record<string, string> = {
    social: join(REPORTS_DIR, `social-${date}.jsonl`),
    research: join(REPORTS_DIR, `research-ramsay-${date}.jsonl`),
  };

  const logFile = logFiles[pipeline];
  if (!logFile || !existsSync(logFile)) return [];

  try {
    const content = readFileSync(logFile, "utf-8");
    const lines = content.trim().split("\n");
    const events: LogEvent[] = [];

    for (const line of lines.slice(-limit)) {
      if (!line.startsWith("{")) continue;
      try {
        events.push(JSON.parse(line));
      } catch { /* skip bad lines */ }
    }
    return events;
  } catch {
    return [];
  }
}

// ── Stderr reader (the human-readable logs) ──────────────────────────────

function readStderrLog(pipeline: string, limit = 30): string[] {
  const stderrFiles: Record<string, string[]> = {
    social: [
      join(REPORTS_DIR, "social-morning-stderr.log"),
      join(REPORTS_DIR, "social-midday-stderr.log"),
      join(REPORTS_DIR, "social-evening-stderr.log"),
    ],
  };

  const files = stderrFiles[pipeline] || [];
  const lines: string[] = [];

  for (const f of files) {
    if (!existsSync(f)) continue;
    try {
      const content = readFileSync(f, "utf-8");
      const fileLines = content.trim().split("\n").filter(l => l.trim());
      lines.push(...fileLines);
    } catch { /* skip */ }
  }

  return lines.slice(-limit);
}

// ── Artifact reader ──────────────────────────────────────────────────────

function readArtifacts(): Record<string, any> {
  const artifacts: Record<string, any> = {};

  // Brief
  const briefPath = join(DATA_DIR, "social-brief.json");
  if (existsSync(briefPath)) {
    try { artifacts.brief = JSON.parse(readFileSync(briefPath, "utf-8")); } catch {}
  }

  // Art concept
  const conceptPath = join(DRAFTS_DIR, "art-concept.json");
  if (existsSync(conceptPath)) {
    try { artifacts.art_concept = JSON.parse(readFileSync(conceptPath, "utf-8")); } catch {}
  }

  // Art review
  const reviewPath = join(DRAFTS_DIR, "art-review.json");
  if (existsSync(reviewPath)) {
    try { artifacts.art_review = JSON.parse(readFileSync(reviewPath, "utf-8")); } catch {}
  }

  // Images
  for (const [key, filename] of [
    ["linkedin_image", "linkedin-image.png"],
    ["bluesky_image", "bluesky-image.jpg"],
  ] as const) {
    const imgPath = join(DRAFTS_DIR, filename);
    if (existsSync(imgPath)) {
      const stat = statSync(imgPath);
      artifacts[key] = {
        path: imgPath,
        size_kb: Math.round(stat.size / 1024),
        modified: new Date(stat.mtimeMs).toLocaleTimeString("en-US", { hour12: false }),
        age_s: Math.round((Date.now() - stat.mtimeMs) / 1000),
      };
    }
  }

  // Drafts
  for (const platform of ["x", "bluesky", "linkedin"]) {
    const draftPath = join(DRAFTS_DIR, `${platform}-draft.md`);
    if (existsSync(draftPath)) {
      const stat = statSync(draftPath);
      artifacts[`${platform}_draft`] = {
        content: readFileSync(draftPath, "utf-8"),
        modified: new Date(stat.mtimeMs).toLocaleTimeString("en-US", { hour12: false }),
      };
    }
  }

  return artifacts;
}

// ── DB queries ───────────────────────────────────────────────────────────

function readPostsToday(): any[] {
  if (!existsSync(DB_PATH)) return [];
  try {
    const db = new Database(DB_PATH, { readonly: true });
    const date = new Date().toISOString().split("T")[0];
    const rows = db.query(
      "SELECT date, platform, anchor_text, posted, created_at FROM social_posts WHERE date = ? ORDER BY created_at"
    ).all(date);
    db.close();
    return rows;
  } catch {
    return [];
  }
}

// ── Approval status ─────────────────────────────────────────────────────

function readApprovalStatus(): any[] {
  if (!existsSync(DB_PATH)) return [];
  try {
    const db = new Database(DB_PATH, { readonly: true });
    const date = new Date().toISOString().split("T")[0];
    const rows = db.query(
      `SELECT token, pipeline, stage, status, created_at, decided_at
       FROM approval_reviews
       WHERE date(created_at) = ?
       ORDER BY created_at DESC
       LIMIT 10`
    ).all(date);
    db.close();
    return rows;
  } catch {
    return [];
  }
}

// ── Build dashboard state ────────────────────────────────────────────────

async function getDashboardState() {
  const procs = await scanProcesses();
  return {
    ts: new Date().toLocaleTimeString("en-US", { hour12: false }),
    processes: procs,
    social_events: readLogs("social"),
    research_events: readLogs("research"),
    stderr_lines: readStderrLog("social"),
    artifacts: readArtifacts(),
    posts_today: readPostsToday(),
    approvals: readApprovalStatus(),
  };
}

// ── WebSocket clients ────────────────────────────────────────────────────

const wsClients = new Set<any>();

// Broadcast state every 3 seconds
setInterval(async () => {
  if (wsClients.size === 0) return;
  const state = await getDashboardState();
  const msg = JSON.stringify(state);
  for (const ws of wsClients) {
    try { ws.send(msg); } catch { wsClients.delete(ws); }
  }
}, 3000);

// ── Bun server ───────────────────────────────────────────────────────────

const htmlPath = join(import.meta.dir, "index.html");

Bun.serve({
  port: PORT,
  async fetch(req, server) {
    const url = new URL(req.url);

    // WebSocket upgrade
    if (url.pathname === "/ws") {
      if (server.upgrade(req)) return;
      return new Response("WebSocket upgrade failed", { status: 400 });
    }

    // API endpoints
    if (url.pathname === "/api/state") {
      return Response.json(await getDashboardState());
    }

    if (url.pathname === "/api/image/linkedin") {
      const p = join(DRAFTS_DIR, "linkedin-image.png");
      if (!existsSync(p)) return new Response("Not found", { status: 404 });
      return new Response(Bun.file(p), {
        headers: { "Content-Type": "image/png", "Cache-Control": "no-cache" },
      });
    }

    if (url.pathname === "/api/image/bluesky") {
      const p = join(DRAFTS_DIR, "bluesky-image.jpg");
      if (!existsSync(p)) return new Response("Not found", { status: 404 });
      return new Response(Bun.file(p), {
        headers: { "Content-Type": "image/jpeg", "Cache-Control": "no-cache" },
      });
    }

    if (url.pathname === "/api/kill" && req.method === "POST") {
      const pid = url.searchParams.get("pid");
      if (pid && /^\d+$/.test(pid)) {
        try {
          process.kill(parseInt(pid, 10), "SIGTERM");
          return Response.json({ ok: true, killed: pid });
        } catch (e: any) {
          return Response.json({ ok: false, error: e.message });
        }
      }
      return Response.json({ ok: false, error: "invalid or missing pid" });
    }

    if (url.pathname === "/api/trigger" && req.method === "POST") {
      const pipeline = url.searchParams.get("pipeline");
      const validPipelines: Record<string, string[]> = {
        "social": ["bash", "run-social.sh", "ramsay"],
        "social-skip-curator": ["bash", "run-social.sh", "ramsay", "--skip-curator"],
        "social-skip-art": ["bash", "run-social.sh", "ramsay", "--skip-art"],
        "social-art-only": ["bash", "run-social.sh", "ramsay", "--skip-curator", "--skip-post"],
      };

      const cmd = pipeline ? validPipelines[pipeline] : null;
      if (!cmd) {
        return Response.json({ ok: false, error: "invalid pipeline" });
      }

      try {
        const proc = Bun.spawn(cmd, {
          cwd: PROJECT_DIR,
          stdout: "ignore",
          stderr: "ignore",
        });
        return Response.json({ ok: true, pipeline, pid: proc.pid });
      } catch (e: any) {
        return Response.json({ ok: false, error: e.message });
      }
    }

    // Serve dashboard HTML
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return new Response(Bun.file(htmlPath), {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    return new Response("Not found", { status: 404 });
  },

  websocket: {
    open(ws: any) {
      wsClients.add(ws);
      getDashboardState().then(state => {
        try { ws.send(JSON.stringify(state)); } catch {}
      });
    },
    close(ws: any) {
      wsClients.delete(ws);
    },
    message() {}, // No client messages expected
  },
});

console.log(`\x1b[35m  mindpattern dashboard\x1b[0m → http://localhost:${PORT}`);
console.log(`  WebSocket → ws://localhost:${PORT}/ws`);
console.log(`  Press Ctrl+C to stop\n`);
