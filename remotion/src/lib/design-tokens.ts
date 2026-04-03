/**
 * MindPattern design tokens
 * Infographic style: light backgrounds, category-coded colors,
 * information-dense, professional but vibrant.
 *
 * Ported from Rayni's design-tokens.ts architecture,
 * adapted for MindPattern's animated social media GIFs.
 */

export const colors = {
  // Core
  white: "#ffffff",
  black: "#0F172A",
  bg: "#FAFBFC",
  bgWarm: "#F1F3F5",

  // Text
  text: "#0F172A",
  textMuted: "#64748B",
  textBody: "#475569",
  textLight: "#94A3B8",

  // Dark bars (Rayni-navy style headers)
  darkBar: "#0F172A",
  darkBarText: "#E2E8F0",

  // Neutral cards
  cardBg: "#F8FAFC",
  cardBorder: "#E2E8F0",
  cardBorderHover: "#CBD5E1",
} as const

// Category accent colors - each topic gets its own
export type AccentColor =
  | "blue"
  | "green"
  | "violet"
  | "orange"
  | "red"
  | "cyan"
  | "amber"
  | "pink"

export const accentColors: Record<AccentColor, string> = {
  blue: "#2563EB",     // AI / Models
  green: "#059669",    // Coding / Dev
  violet: "#7C3AED",   // Data / Research
  orange: "#EA580C",   // Infrastructure
  red: "#DC2626",      // Alerts / Breaking
  cyan: "#0891B2",     // Tools / Platforms
  amber: "#D97706",    // Trends / Analysis
  pink: "#DB2777",     // Social / Community
}

// Soft glow versions for backgrounds
export const glowColors: Record<AccentColor, string> = {
  blue: "rgba(37, 99, 235, 0.15)",
  green: "rgba(5, 150, 105, 0.15)",
  violet: "rgba(124, 58, 237, 0.15)",
  orange: "rgba(234, 88, 12, 0.15)",
  red: "rgba(220, 38, 38, 0.15)",
  cyan: "rgba(8, 145, 178, 0.15)",
  amber: "rgba(217, 119, 6, 0.15)",
  pink: "rgba(219, 39, 119, 0.15)",
}

// Pill background colors (lighter, for category labels)
export const pillColors: Record<AccentColor, string> = {
  blue: "#DBEAFE",
  green: "#D1FAE5",
  violet: "#EDE9FE",
  orange: "#FFEDD5",
  red: "#FEE2E2",
  cyan: "#CFFAFE",
  amber: "#FEF3C7",
  pink: "#FCE7F3",
}

// Typography
export const fonts = {
  display: "'Space Grotesk', system-ui, sans-serif",
  body: "'Geist', 'Inter', system-ui, sans-serif",
  mono: "'Geist Mono', 'JetBrains Mono', monospace",
}

export const fontWeights = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
}

export const fontSizes = {
  xs: 11,
  sm: 13,
  base: 15,
  lg: 18,
  xl: 22,
  "2xl": 28,
  "3xl": 36,
  "4xl": 48,
  "5xl": 60,
  "6xl": 80,
  "7xl": 96,
}

// Animation timing (in frames at 15fps for GIFs, 30fps for video)
export const timing = {
  gifFps: 15,
  videoFps: 30,
  staggerDelay: 3,        // frames between staggered items (at 15fps)
  entranceDuration: 8,    // frames for fade+slide entrance
  fadeOutDuration: 6,     // frames for loop fade-out
}

// Spacing (8px base)
export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  "2xl": 48,
  "3xl": 64,
  "4xl": 80,
}
