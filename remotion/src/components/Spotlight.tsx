import React from "react"
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing, spring } from "remotion"
import { colors, accentColors, fonts, fontSizes, fontWeights, type AccentColor } from "../lib/design-tokens"
import { GradientBackground } from "./GradientBackground"
import { CategoryPill } from "./CategoryPill"

interface SpotlightProps {
  stat: string
  label: string
  category: string
  accent: AccentColor
  source?: string
  isNumeric?: boolean
  numericTarget?: number
}

function seeded(seed: number): number {
  const x = Math.sin(seed * 9301 + 49297) * 49297
  return x - Math.floor(x)
}

const particles = Array.from({ length: 20 }, (_, i) => {
  const angle = (i / 20) * Math.PI * 2 + seeded(i * 7) * 0.3
  const distance = 100 + seeded(i * 13) * 160
  const size = 3 + seeded(i * 19) * 6
  const delay = Math.floor(seeded(i * 31) * 6)
  return { angle, distance, size, delay }
})

export const Spotlight: React.FC<SpotlightProps> = ({
  stat, label, category, accent, source,
  isNumeric = false, numericTarget = 0,
}) => {
  const frame = useCurrentFrame()
  const { fps, durationInFrames } = useVideoConfig()
  const ac = accentColors[accent]

  // Decorative grid dots
  const gridOpacity = interpolate(frame, [0, 10], [0, 0.06], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Scan line (horizontal rule drawing across)
  const scanX = interpolate(frame, [2, 14], [-720, 720], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Corner accents draw
  const cornerLen = interpolate(frame, [4, 16], [0, 80], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Category pill
  const pillSpring = spring({
    frame: Math.max(0, frame - 6), fps,
    config: { damping: 14, stiffness: 150, mass: 0.6 },
  })

  // Monospace section label
  const sectionLabelOp = interpolate(frame, [8, 14], [0, 0.4], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Horizontal rule under pill
  const ruleWidth = interpolate(frame, [10, 20], [0, 200], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Stat
  const statSpring = spring({
    frame: Math.max(0, frame - 14), fps,
    config: { damping: 10, stiffness: 100, mass: 0.8 },
  })
  const statOp = interpolate(frame, [14, 20], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Number counting
  const countProg = interpolate(frame, [14, 14 + fps], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
  const displayStat = isNumeric ? `${Math.round(countProg * numericTarget)}` : stat

  // Particles
  const burstActive = frame >= 16

  // Bottom accent rule
  const rule2Width = interpolate(frame, [22, 30], [0, 120], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Label
  const labelOp = interpolate(frame, [26, 34], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
  const labelY = interpolate(frame, [26, 34], [20, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Source + branding
  const sourceOp = interpolate(frame, [36, 42], [0, 0.45], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Loop fade
  const loopFade = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  return (
    <GradientBackground accent={accent}>
      <AbsoluteFill style={{ opacity: loopFade }}>
        {/* Grid dots */}
        <svg width="720" height="720" style={{ position: "absolute" }}>
          {Array.from({ length: 100 }, (_, i) => {
            const col = i % 10; const row = Math.floor(i / 10)
            return <circle key={i} cx={col * 72 + 36} cy={row * 72 + 36} r={1.5} fill={ac} opacity={gridOpacity} />
          })}
        </svg>

        {/* Scan line flash */}
        <div style={{
          position: "absolute", top: "50%", left: scanX, width: 200, height: 1,
          background: `linear-gradient(90deg, transparent, ${ac}40, transparent)`,
          opacity: frame < 14 ? 0.6 : 0,
        }} />

        {/* Corner accent lines */}
        <svg width="720" height="720" style={{ position: "absolute" }}>
          {/* Top-left */}
          <line x1="32" y1="32" x2={32 + cornerLen} y2="32" stroke={ac} strokeWidth="1.5" opacity="0.2" />
          <line x1="32" y1="32" x2="32" y2={32 + cornerLen * 0.6} stroke={ac} strokeWidth="1.5" opacity="0.2" />
          {/* Top-right */}
          <line x1="688" y1="32" x2={688 - cornerLen} y2="32" stroke={ac} strokeWidth="1.5" opacity="0.2" />
          <line x1="688" y1="32" x2="688" y2={32 + cornerLen * 0.6} stroke={ac} strokeWidth="1.5" opacity="0.2" />
          {/* Bottom-left */}
          <line x1="32" y1="688" x2={32 + cornerLen} y2="688" stroke={ac} strokeWidth="1.5" opacity="0.2" />
          <line x1="32" y1="688" x2="32" y2={688 - cornerLen * 0.6} stroke={ac} strokeWidth="1.5" opacity="0.2" />
          {/* Bottom-right */}
          <line x1="688" y1="688" x2={688 - cornerLen} y2="688" stroke={ac} strokeWidth="1.5" opacity="0.2" />
          <line x1="688" y1="688" x2="688" y2={688 - cornerLen * 0.6} stroke={ac} strokeWidth="1.5" opacity="0.2" />
        </svg>

        {/* Particles */}
        {burstActive && particles.map((p, i) => {
          const lf = frame - 16 - p.delay
          if (lf < 0) return null
          const prog = interpolate(lf, [0, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) })
          const x = 360 + Math.cos(p.angle) * p.distance * prog
          const y = 300 + Math.sin(p.angle) * p.distance * prog
          const op = interpolate(prog, [0, 0.15, 0.5, 1], [0, 0.5, 0.3, 0])
          return <div key={i} style={{ position: "absolute", left: x - p.size / 2, top: y - p.size / 2, width: p.size, height: p.size, borderRadius: "50%", backgroundColor: ac, opacity: op }} />
        })}

        {/* Main content */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", padding: 56 }}>

          {/* Monospace section label */}
          <div style={{
            opacity: sectionLabelOp,
            fontFamily: fonts.mono, fontSize: 10, fontWeight: 500,
            color: colors.textLight, letterSpacing: "0.2em", textTransform: "uppercase",
            marginBottom: 12,
          }}>
            // {category.toLowerCase().replace(/ /g, "_")}
          </div>

          {/* Category pill */}
          <div style={{
            opacity: pillSpring,
            transform: `translateY(${interpolate(pillSpring, [0, 1], [-15, 0])}px) scale(${pillSpring})`,
            marginBottom: 20,
          }}>
            <CategoryPill label={category} accent={accent} startFrame={0} variant="dark" />
          </div>

          {/* Top rule */}
          <div style={{ width: ruleWidth, height: 1, backgroundColor: ac, opacity: 0.25, marginBottom: 32 }} />

          {/* Stat */}
          <div style={{
            opacity: statOp, transform: `scale(${statSpring})`,
            fontFamily: fonts.display, fontSize: isNumeric ? fontSizes["7xl"] : fontSizes["6xl"],
            fontWeight: fontWeights.bold, color: ac, lineHeight: 1, letterSpacing: "-3px", textAlign: "center",
          }}>
            {displayStat}
            {isNumeric && <span style={{ fontSize: fontSizes["4xl"], opacity: 0.7 }}>%</span>}
          </div>

          {/* Bottom rule */}
          <div style={{ width: rule2Width, height: 1, backgroundColor: ac, opacity: 0.15, marginTop: 28, marginBottom: 28 }} />

          {/* Label */}
          <div style={{
            opacity: labelOp, transform: `translateY(${labelY}px)`,
            fontFamily: fonts.body, fontSize: fontSizes.xl, fontWeight: fontWeights.medium,
            color: colors.text, maxWidth: 460, textAlign: "center", lineHeight: 1.45,
          }}>
            {label}
          </div>

          {/* Source */}
          {source && (
            <div style={{
              opacity: sourceOp,
              fontFamily: fonts.mono, fontSize: 9, color: colors.textLight,
              marginTop: 20, letterSpacing: "0.08em", textTransform: "uppercase",
              borderTop: `1px solid ${colors.cardBorder}`, paddingTop: 10,
            }}>
              src: {source}
            </div>
          )}
        </div>

        {/* Branding */}
        <div style={{
          position: "absolute", bottom: 20, right: 24,
          display: "flex", alignItems: "center", gap: 8,
          opacity: interpolate(frame, [10, 20], [0, 0.3], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}>
          <div style={{ width: 16, height: 1, backgroundColor: ac, opacity: 0.5 }} />
          <span style={{
            fontFamily: fonts.mono, fontSize: 9, fontWeight: 500,
            color: colors.textLight, letterSpacing: "0.12em", textTransform: "uppercase",
          }}>
            mindpattern
          </span>
        </div>

        {/* Top-left mono timestamp feel */}
        <div style={{
          position: "absolute", top: 20, left: 24,
          opacity: interpolate(frame, [12, 20], [0, 0.2], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          fontFamily: fonts.mono, fontSize: 9, color: colors.textLight,
          letterSpacing: "0.1em",
        }}>
          2026.04.03
        </div>
      </AbsoluteFill>
    </GradientBackground>
  )
}
