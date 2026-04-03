import React from "react"
import { Composition } from "remotion"
import { KineticTypography } from "./components/Typography"
import { DataViz } from "./components/DataViz"
import { Spotlight } from "./components/Spotlight"
import { Infographic } from "./components/Infographic"

const FPS = 15
const SHORT = FPS * 6    // 6 seconds (stat reveals)
const LONG = FPS * 10    // 10 seconds (infographics, read time)

export const Root: React.FC = () => {
  return (
    <>
      {/* ── REAL POST: Anthropic vs OpenAI Acquisitions (infographic) ── */}
      <Composition
        id="Post-Acquisitions"
        component={Infographic}
        durationInFrames={LONG}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          headline: "First Acquisitions Reveal the Strategy",
          subtitle: "Anthropic and OpenAI both made their first acquisition in the same week. Neither bought compute or models.",
          categories: [
            {
              title: "Anthropic",
              items: [
                "Coefficient Bio — $400M",
                "10-person biotech regulatory team",
                "Bet: trust, safety, compliance",
                "The bottleneck is regulation",
              ],
              accent: "blue" as const,
            },
            {
              title: "OpenAI",
              items: [
                "AI debate show format — $150M",
                "Entertainment media bet",
                "Bet: consumer attention",
                "The bottleneck is distribution",
              ],
              accent: "violet" as const,
            },
            {
              title: "What They Didn't Buy",
              items: [
                "No compute infrastructure",
                "No competing models",
                "No research teams",
                "No enterprise customers",
              ],
              accent: "orange" as const,
            },
            {
              title: "What This Means",
              items: [
                "The model race is over (for now)",
                "Moats are built outside the lab",
                "Compliance > capability",
                "Distribution > performance",
              ],
              accent: "green" as const,
            },
          ],
          footerText: "src: Anthropic + OpenAI filings, April 2026",
        }}
      />

      {/* ── REAL POST: Sora Economics (infographic) ── */}
      <Composition
        id="Post-SoraEconomics"
        component={Infographic}
        durationInFrames={LONG}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          headline: "Sora: The Numbers Don't Add Up",
          subtitle: "$2.1M lifetime revenue vs $1M/day in compute. Altman called Disney's CEO personally.",
          categories: [
            {
              title: "Sora Revenue",
              items: [
                "$2.1M total lifetime revenue",
                "Less than 3 days of compute cost",
                "Consumer pricing can't cover GPU burn",
              ],
              accent: "red" as const,
            },
            {
              title: "Sora Costs",
              items: [
                "$1M per day in compute",
                "$365M annualized burn rate",
                "Each video costs more than users pay",
              ],
              accent: "orange" as const,
            },
            {
              title: "Meanwhile: Claude",
              items: [
                "$8K in tokens this year",
                "4 products shipped and running",
                "Revenue-positive from month 1",
              ],
              accent: "blue" as const,
            },
            {
              title: "The Lesson",
              items: [
                "Spectacle ≠ product-market fit",
                "Text AI ships value today",
                "Video AI is still pre-revenue",
              ],
              accent: "green" as const,
            },
          ],
          footerText: "src: internal estimates + public filings",
        }}
      />

      {/* ── REAL POST: Claude Code Leak (spotlight + long hold) ── */}
      <Composition
        id="Post-ClaudeCodeLeak"
        component={Spotlight}
        durationInFrames={SHORT}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          stat: "512K",
          label: "lines of Anthropic source code exposed. Not a hack. Bun's default behavior. Bug open 20 days.",
          category: "SECURITY",
          accent: "red" as const,
          source: "Bun source map leak — March 2026",
        }}
      />

      {/* ── REAL POST: Bun Leak (infographic) ── */}
      <Composition
        id="Post-BunLeak"
        component={Infographic}
        durationInFrames={LONG}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          headline: "Bun Source Maps: Default Behavior, Not an Exploit",
          subtitle: "The bug had been open for 20 days. Someone checked the Claude Code npm package and pulled the full source.",
          categories: [
            {
              title: "What Happened",
              items: [
                "Bun includes source maps by default",
                "Claude Code shipped with them",
                "512K lines of Anthropic source visible",
                "Not a hack — a build tool default",
              ],
              accent: "red" as const,
            },
            {
              title: "Who's Affected",
              items: [
                "Anyone using Bun for npm packages",
                "Any package without explicit .npmignore",
                "Source maps expose full original code",
              ],
              accent: "orange" as const,
            },
            {
              title: "What To Do",
              items: [
                "Check your .npmignore immediately",
                'Add "sourceMappingURL" to ignore',
                "Audit published package contents",
                "Use npm pack --dry-run to verify",
              ],
              accent: "blue" as const,
            },
            {
              title: "Bigger Picture",
              items: [
                "Build tool defaults are security surface",
                "20 days open = many others affected",
                "Supply chain risk from dev tooling",
              ],
              accent: "violet" as const,
            },
          ],
          footerText: "src: alex000kim.com + bun github issue tracker",
        }}
      />

      {/* ── REAL POST: Anthropic $400M (spotlight) ── */}
      <Composition
        id="Post-CoefficientBio"
        component={Spotlight}
        durationInFrames={SHORT}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          stat: "$400M",
          label: "for 10 people. Not compute, not researchers. A stealth biotech regulatory team. A company's first acquisition reveals its theory of constraints.",
          category: "ANTHROPIC",
          accent: "blue" as const,
          source: "Coefficient Bio Acquisition — April 2026",
        }}
      />

      {/* ── Base compositions ── */}
      <Composition
        id="Spotlight"
        component={Spotlight}
        durationInFrames={SHORT}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          stat: "10x",
          label: "faster with AI-assisted coding tools",
          category: "AI TOOLS",
          accent: "blue" as const,
        }}
      />

      <Composition
        id="DataViz"
        component={DataViz}
        durationInFrames={SHORT}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          title: "AI Agent Adoption by Category",
          values: [85, 72, 58, 43, 31],
          labels: ["Code", "Research", "Writing", "Design", "Ops"],
          category: "AI AGENTS",
          accent: "green" as const,
          unit: "%",
        }}
      />

      <Composition
        id="KineticTypography"
        component={KineticTypography}
        durationInFrames={SHORT}
        fps={FPS}
        width={720}
        height={720}
        defaultProps={{
          headline: "AI agents are replacing entire SaaS workflows",
          category: "TREND ANALYSIS",
          accent: "orange" as const,
          subtext: "From 12 tools down to 1 agent.",
        }}
      />
    </>
  )
}
