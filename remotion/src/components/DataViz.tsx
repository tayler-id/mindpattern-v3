import React from "react"
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing, spring } from "remotion"
import { colors, accentColors, fonts, fontSizes, fontWeights, type AccentColor } from "../lib/design-tokens"
import { fadeIn, slideUp, fadeOut } from "../lib/utils"
import { GradientBackground } from "./GradientBackground"
import { CategoryPill } from "./CategoryPill"

interface DataVizProps {
  title: string
  values: number[]
  labels: string[]
  category: string
  accent: AccentColor
  unit?: string
}

// Decorative horizontal grid lines
const gridLines = [0.2, 0.4, 0.6, 0.8]

export const DataViz: React.FC<DataVizProps> = ({
  title,
  values,
  labels,
  category,
  accent,
  unit = "",
}) => {
  const frame = useCurrentFrame()
  const { fps, durationInFrames } = useVideoConfig()

  const maxValue = Math.max(...values)
  const barCount = values.length
  const chartWidth = 540
  const barGap = 20
  const barWidth = Math.min(72, (chartWidth - barGap * (barCount - 1)) / barCount)
  const chartHeight = 300
  const chartLeft = (720 - chartWidth) / 2
  const chartTop = 220
  const accentColor = accentColors[accent]
  const loopFade = fadeOut(frame, durationInFrames, 8)

  // Phase 1: Category pill (frame 2)
  const pillSpring = spring({
    frame: Math.max(0, frame - 2),
    fps,
    config: { damping: 14, stiffness: 150, mass: 0.6 },
  })

  // Phase 2: Title wipes in (frame 4-12)
  const titleClip = interpolate(frame, [4, 14], [100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Phase 3: Grid lines draw (frame 8-16)
  const gridProgress = interpolate(frame, [8, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Phase 4: Baseline draws (frame 10-14)
  const baselineWidth = interpolate(frame, [10, 16], [0, chartWidth], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  // Phase 5: Bars grow with staggered springs (frame 12+)

  // Phase 6: Summary stat (frame 35+)
  const summaryOpacity = interpolate(frame, [38, 44], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  })
  const summaryY = interpolate(frame, [38, 46], [15, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  })

  const avgValue = Math.round(values.reduce((a, b) => a + b, 0) / values.length)

  return (
    <GradientBackground accent={accent}>
      <AbsoluteFill style={{ opacity: loopFade }}>
        {/* Content */}
        <div style={{ padding: "44px 52px" }}>
          {/* Category pill */}
          <div
            style={{
              opacity: pillSpring,
              transform: `translateY(${interpolate(pillSpring, [0, 1], [-15, 0])}px)`,
              marginBottom: 12,
            }}
          >
            <CategoryPill label={category} accent={accent} startFrame={0} variant="dark" />
          </div>

          {/* Title with wipe reveal */}
          <div
            style={{
              clipPath: `inset(0 ${titleClip}% 0 0)`,
              fontFamily: fonts.display,
              fontSize: fontSizes["2xl"],
              fontWeight: fontWeights.bold,
              color: colors.text,
              letterSpacing: "-0.5px",
              lineHeight: 1.3,
              marginBottom: 8,
            }}
          >
            {title}
          </div>
        </div>

        {/* Chart area */}
        <svg
          width="720"
          height="400"
          viewBox="0 0 720 400"
          style={{ position: "absolute", top: chartTop - 30, left: 0 }}
        >
          {/* Grid lines */}
          {gridLines.map((pct, i) => {
            const y = chartHeight * (1 - pct) + 30
            const lineLen = chartWidth * gridProgress
            return (
              <g key={i}>
                <line
                  x1={chartLeft}
                  y1={y}
                  x2={chartLeft + lineLen}
                  y2={y}
                  stroke={colors.cardBorder}
                  strokeWidth="1"
                  strokeDasharray="4 4"
                  opacity={0.6}
                />
                {/* Grid label */}
                <text
                  x={chartLeft - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontFamily={fonts.mono.split(",")[0].replace(/'/g, "")}
                  fontSize="10"
                  fill={colors.textLight}
                  opacity={gridProgress}
                >
                  {Math.round(maxValue * pct)}{unit}
                </text>
              </g>
            )
          })}

          {/* Baseline */}
          <line
            x1={chartLeft}
            y1={chartHeight + 30}
            x2={chartLeft + baselineWidth}
            y2={chartHeight + 30}
            stroke={colors.text}
            strokeWidth="2"
            opacity={0.2}
          />

          {/* Bars */}
          {values.map((value, i) => {
            const barDelay = 14 + i * 3
            const barSpring = spring({
              frame: Math.max(0, frame - barDelay),
              fps,
              config: { damping: 12, stiffness: 80, mass: 0.7 },
            })

            const targetHeight = (value / maxValue) * chartHeight
            const currentHeight = targetHeight * barSpring
            const barX = chartLeft + i * (barWidth + barGap) + (chartWidth - barCount * (barWidth + barGap) + barGap) / 2
            const barY = chartHeight + 30 - currentHeight

            // Counting value
            const countProgress = interpolate(
              frame,
              [barDelay, barDelay + fps * 0.6],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }
            )
            const displayVal = Math.round(countProgress * value)

            return (
              <g key={i}>
                {/* Bar */}
                <rect
                  x={barX}
                  y={barY}
                  width={barWidth}
                  height={currentHeight}
                  rx={4}
                  fill={accentColor}
                />
                {/* Bar highlight */}
                <rect
                  x={barX}
                  y={barY}
                  width={barWidth}
                  height={Math.min(currentHeight, 20)}
                  rx={4}
                  fill="white"
                  opacity={0.15}
                />

                {/* Value label above bar */}
                {barSpring > 0.3 && (
                  <text
                    x={barX + barWidth / 2}
                    y={barY - 10}
                    textAnchor="middle"
                    fontFamily={fonts.mono.split(",")[0].replace(/'/g, "")}
                    fontSize="14"
                    fontWeight="700"
                    fill={accentColor}
                    opacity={interpolate(barSpring, [0.3, 0.6], [0, 1], {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    })}
                  >
                    {displayVal}{unit}
                  </text>
                )}

                {/* Label below baseline */}
                {barSpring > 0.2 && (
                  <text
                    x={barX + barWidth / 2}
                    y={chartHeight + 50}
                    textAnchor="middle"
                    fontFamily={fonts.body.split(",")[0].replace(/'/g, "")}
                    fontSize="12"
                    fontWeight="600"
                    fill={colors.textMuted}
                    opacity={interpolate(barSpring, [0.2, 0.5], [0, 1], {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    })}
                  >
                    {labels[i] || ""}
                  </text>
                )}
              </g>
            )
          })}
        </svg>

        {/* Summary stat at bottom */}
        <div
          style={{
            position: "absolute",
            bottom: 56,
            left: 52,
            right: 52,
            display: "flex",
            alignItems: "center",
            gap: 12,
            opacity: summaryOpacity,
            transform: `translateY(${summaryY}px)`,
          }}
        >
          <div
            style={{
              width: 4,
              height: 32,
              backgroundColor: accentColor,
              borderRadius: 2,
            }}
          />
          <div>
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: fontSizes.sm,
                fontWeight: fontWeights.bold,
                color: accentColor,
              }}
            >
              AVG: {avgValue}{unit}
            </div>
            <div
              style={{
                fontFamily: fonts.body,
                fontSize: fontSizes.xs,
                color: colors.textMuted,
              }}
            >
              across {barCount} categories
            </div>
          </div>
        </div>

        {/* Branding */}
        <div
          style={{
            position: "absolute",
            bottom: 24,
            right: 28,
            opacity: interpolate(frame, [8, 18], [0, 0.35], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            fontFamily: fonts.display,
            fontSize: fontSizes.xs,
            fontWeight: fontWeights.semibold,
            color: colors.textLight,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
          }}
        >
          mindpattern
        </div>
      </AbsoluteFill>
    </GradientBackground>
  )
}
