import React from "react"
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing, spring } from "remotion"
import { colors, accentColors, pillColors, fonts, fontSizes, fontWeights, type AccentColor } from "../lib/design-tokens"

interface CategoryCard {
  title: string
  items: string[]
  accent: AccentColor
}

interface InfographicProps {
  headline: string
  subtitle?: string
  categories: CategoryCard[]
  footerText?: string
}

/**
 * Multi-card animated infographic.
 * Builds up piece by piece: headline, then cards fly in from alternating
 * sides with staggered timing. Each card has a colored accent bar, title,
 * and bullet items. Dense, information-rich, designed to be saved and shared.
 *
 * 8-10 seconds with a 3-second hold at end for reading.
 */
export const Infographic: React.FC<InfographicProps> = ({
  headline,
  subtitle,
  categories,
  footerText,
}) => {
  const frame = useCurrentFrame()
  const { fps, durationInFrames } = useVideoConfig()
  const holdStart = durationInFrames - fps * 3  // 3 second hold
  const fadeStart = durationInFrames - Math.floor(fps * 0.5)

  // Global fade out only in last 0.5s
  const loopFade = interpolate(frame, [fadeStart, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Phase 1: Background grid (frame 0-6)
  const gridOp = interpolate(frame, [0, 8], [0, 0.04], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Phase 2: Header bar slides down (frame 2-10)
  const headerY = interpolate(frame, [2, 12], [-80, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })
  const headerOp = interpolate(frame, [2, 8], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })

  // Phase 3: Headline wipes in (frame 6-14)
  const headlineClip = interpolate(frame, [6, 16], [100, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Phase 4: Subtitle (frame 10-16)
  const subOp = interpolate(frame, [12, 18], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  })
  const subY = interpolate(frame, [12, 18], [12, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Phase 5: Divider line draws (frame 14-20)
  const dividerW = interpolate(frame, [16, 24], [0, 640], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Layout: 2 columns of cards
  const cols = 2
  const cardWidth = 290
  const cardGap = 20
  const startX = (720 - (cardWidth * cols + cardGap * (cols - 1))) / 2

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg, opacity: loopFade }}>
      {/* Background grid dots */}
      <svg width="720" height="720" style={{ position: "absolute" }}>
        {Array.from({ length: 144 }, (_, i) => {
          const col = i % 12; const row = Math.floor(i / 12)
          return <circle key={i} cx={col * 60 + 30} cy={row * 60 + 30} r={1} fill="#94A3B8" opacity={gridOp} />
        })}
      </svg>

      {/* Corner accents */}
      <svg width="720" height="720" style={{ position: "absolute" }}>
        {[
          { x1: 24, y1: 24, dx: 50, dy: 30 },
          { x1: 696, y1: 24, dx: -50, dy: 30 },
          { x1: 24, y1: 696, dx: 50, dy: -30 },
          { x1: 696, y1: 696, dx: -50, dy: -30 },
        ].map((c, i) => {
          const len = interpolate(frame, [4, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
          return (
            <g key={i} opacity={0.15}>
              <line x1={c.x1} y1={c.y1} x2={c.x1 + c.dx * len} y2={c.y1} stroke="#94A3B8" strokeWidth="1" />
              <line x1={c.x1} y1={c.y1} x2={c.x1} y2={c.y1 + c.dy * len} stroke="#94A3B8" strokeWidth="1" />
            </g>
          )
        })}
      </svg>

      {/* Dark header bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 56,
        backgroundColor: colors.darkBar,
        opacity: headerOp,
        transform: `translateY(${headerY}px)`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 28px",
      }}>
        <span style={{
          fontFamily: fonts.mono, fontSize: 10, fontWeight: 500,
          color: "#64748B", letterSpacing: "0.15em", textTransform: "uppercase",
        }}>
          mindpattern // daily briefing
        </span>
        <span style={{
          fontFamily: fonts.mono, fontSize: 10,
          color: "#475569", letterSpacing: "0.1em",
        }}>
          2026.04.03
        </span>
      </div>

      {/* Headline */}
      <div style={{
        position: "absolute", top: 72, left: 36, right: 36,
        clipPath: `inset(0 ${headlineClip}% 0 0)`,
      }}>
        <h1 style={{
          fontFamily: fonts.display, fontSize: 32, fontWeight: fontWeights.bold,
          color: colors.text, letterSpacing: "-0.5px", lineHeight: 1.2, margin: 0,
        }}>
          {headline}
        </h1>
      </div>

      {/* Subtitle */}
      {subtitle && (
        <div style={{
          position: "absolute", top: 118, left: 36, right: 36,
          opacity: subOp, transform: `translateY(${subY}px)`,
        }}>
          <p style={{
            fontFamily: fonts.body, fontSize: 14, color: colors.textMuted,
            lineHeight: 1.4, margin: 0,
          }}>
            {subtitle}
          </p>
        </div>
      )}

      {/* Divider */}
      <div style={{
        position: "absolute", top: subtitle ? 148 : 120, left: 36,
        width: dividerW, height: 1, backgroundColor: colors.cardBorder,
      }} />

      {/* Category cards */}
      {categories.map((cat, i) => {
        const row = Math.floor(i / cols)
        const col = i % cols
        const cardStart = 20 + i * 6
        const fromLeft = col === 0

        const cardSpring = spring({
          frame: Math.max(0, frame - cardStart), fps,
          config: { damping: 14, stiffness: 100, mass: 0.7 },
        })
        const slideX = interpolate(cardSpring, [0, 1], [fromLeft ? -60 : 60, 0])
        const cardOp = interpolate(frame, [cardStart, cardStart + 6], [0, 1], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp",
        })

        const ac = accentColors[cat.accent]
        const pc = pillColors[cat.accent]
        const cardTop = (subtitle ? 164 : 136) + row * 140

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: cardTop,
              left: startX + col * (cardWidth + cardGap),
              width: cardWidth,
              opacity: cardOp,
              transform: `translateX(${slideX}px)`,
              backgroundColor: colors.white,
              borderRadius: 10,
              border: `1px solid ${colors.cardBorder}`,
              overflow: "hidden",
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
            }}
          >
            {/* Accent bar */}
            <div style={{ height: 3, backgroundColor: ac }} />

            <div style={{ padding: "12px 16px" }}>
              {/* Category title pill */}
              <div style={{
                display: "inline-flex", alignItems: "center",
                padding: "3px 10px", borderRadius: 5,
                backgroundColor: pc, marginBottom: 10,
              }}>
                <span style={{
                  fontFamily: fonts.body, fontSize: 11, fontWeight: fontWeights.bold,
                  color: ac, letterSpacing: "0.03em", textTransform: "uppercase",
                }}>
                  {cat.title}
                </span>
              </div>

              {/* Items */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {cat.items.map((item, j) => {
                  const itemStart = cardStart + 4 + j * 2
                  const itemOp = interpolate(frame, [itemStart, itemStart + 4], [0, 1], {
                    extrapolateLeft: "clamp", extrapolateRight: "clamp",
                  })
                  const itemX = interpolate(frame, [itemStart, itemStart + 4], [10, 0], {
                    extrapolateLeft: "clamp", extrapolateRight: "clamp",
                    easing: Easing.out(Easing.cubic),
                  })

                  return (
                    <div key={j} style={{
                      opacity: itemOp, transform: `translateX(${itemX}px)`,
                      display: "flex", alignItems: "flex-start", gap: 7,
                    }}>
                      <div style={{
                        width: 5, height: 5, borderRadius: "50%",
                        backgroundColor: ac, flexShrink: 0, marginTop: 5,
                      }} />
                      <span style={{
                        fontFamily: fonts.body, fontSize: 12,
                        color: colors.textBody, lineHeight: 1.35,
                      }}>
                        {item}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )
      })}

      {/* Footer */}
      {footerText && (
        <div style={{
          position: "absolute", bottom: 24, left: 36, right: 36,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          opacity: interpolate(frame, [durationInFrames - fps * 3.5, durationInFrames - fps * 3], [0, 0.5], {
            extrapolateLeft: "clamp", extrapolateRight: "clamp",
          }),
        }}>
          <span style={{
            fontFamily: fonts.mono, fontSize: 10, color: colors.textLight,
            letterSpacing: "0.05em",
          }}>
            {footerText}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 12, height: 1, backgroundColor: colors.textLight, opacity: 0.4 }} />
            <span style={{
              fontFamily: fonts.mono, fontSize: 9, color: colors.textLight,
              letterSpacing: "0.12em", textTransform: "uppercase",
            }}>
              mindpattern
            </span>
          </div>
        </div>
      )}
    </AbsoluteFill>
  )
}
