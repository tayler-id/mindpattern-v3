import React from "react"
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion"
import { colors, accentColors, fonts, fontSizes, fontWeights, type AccentColor } from "../lib/design-tokens"
import { fadeIn, slideUp, fadeOut, scaleIn } from "../lib/utils"
import { GradientBackground } from "./GradientBackground"
import { CategoryPill } from "./CategoryPill"

interface KineticTypographyProps {
  headline: string
  category: string
  accent: AccentColor
  subtext?: string
}

/**
 * Kinetic Typography composition.
 * Words appear with staggered fade+slide on light background.
 * Last word in accent color for emphasis.
 * Information-dense feel with category context.
 */
export const KineticTypography: React.FC<KineticTypographyProps> = ({
  headline,
  category,
  accent,
  subtext,
}) => {
  const frame = useCurrentFrame()
  const { fps, durationInFrames } = useVideoConfig()

  const words = headline.split(" ")
  const framesPerWord = Math.max(2, Math.floor((fps * 1.5) / words.length))
  const loopFade = fadeOut(frame, durationInFrames, 6)

  return (
    <GradientBackground accent={accent}>
      <AbsoluteFill
        style={{
          padding: 60,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          opacity: loopFade,
        }}
      >
        {/* Category pill */}
        <div style={{ marginBottom: 40 }}>
          <CategoryPill label={category} accent={accent} startFrame={2} variant="dark" />
        </div>

        {/* Words */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "8px 14px",
            maxWidth: 600,
          }}
        >
          {words.map((word, i) => {
            const wordStart = 6 + i * framesPerWord
            const opacity = fadeIn(frame, wordStart, 6)
            const translateY = slideUp(frame, wordStart, 6, 20)
            const isLast = i === words.length - 1

            return (
              <span
                key={i}
                style={{
                  opacity,
                  transform: `translateY(${translateY}px)`,
                  fontFamily: fonts.display,
                  fontSize: fontSizes["4xl"],
                  fontWeight: fontWeights.bold,
                  color: isLast ? accentColors[accent] : colors.text,
                  lineHeight: 1.2,
                  letterSpacing: "-1px",
                  display: "inline-block",
                }}
              >
                {word}
              </span>
            )
          })}
        </div>

        {/* Subtext */}
        {subtext && (
          <div
            style={{
              opacity: fadeIn(frame, fps * 2.5, 8),
              transform: `translateY(${slideUp(frame, fps * 2.5, 8, 12)}px)`,
              fontFamily: fonts.body,
              fontSize: fontSizes.lg,
              color: colors.textMuted,
              marginTop: 28,
              textAlign: "center",
              maxWidth: 500,
              lineHeight: 1.5,
            }}
          >
            {subtext}
          </div>
        )}

        {/* Branding */}
        <div
          style={{
            position: "absolute",
            bottom: 24,
            right: 32,
            opacity: fadeIn(frame, 8, 10) * 0.4,
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
